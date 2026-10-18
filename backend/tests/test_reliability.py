from types import SimpleNamespace

import pytest

from app.core import metrics
from app.core.config import get_settings
from app.core.db import get_session
from app.models.entities import Diagnosis, PipelineRun
from app.services import claude_client
from app.services.budget import budget_exhausted, tokens_used_today
from app.services.claude_client import CircuitBreaker, ClaudeClient, LLMUnavailable
from app.services.diagnoser import PROMPT_VERSION, diagnose
from tests.conftest import FakeClaude

LOG = "E   ModuleNotFoundError: No module named 'requests'\nProcess completed with exit code 1."


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_breaker_opens_then_half_opens_then_closes():
    clock = Clock()
    b = CircuitBreaker(threshold=3, cooldown_s=60, clock=clock)
    for _ in range(2):
        b.record_failure()
    assert b.allow() and not b.is_open  # below threshold
    b.record_failure()
    assert b.is_open and not b.allow()  # open: calls rejected

    clock.now = 61
    assert b.allow()        # half-open: one trial
    assert not b.allow()    # ...and only one
    b.record_success()
    assert not b.is_open and b.allow()


def test_breaker_reopens_when_trial_fails():
    clock = Clock()
    b = CircuitBreaker(threshold=1, cooldown_s=10, clock=clock)
    b.record_failure()
    clock.now = 11
    assert b.allow()
    b.record_failure()
    assert not b.allow()  # new cooldown starts at t=11
    clock.now = 22
    assert b.allow()


class FailingClaude:
    def structured(self, **_):
        raise RuntimeError("529 overloaded")


def test_diagnose_degrades_to_heuristic_when_claude_fails():
    r = diagnose(LOG, {}, client=FailingClaude())
    assert r.category == "dependency" and r.model == "heuristic"
    assert any("RuntimeError" in w for w in r.warnings)


def test_diagnose_skips_llm_when_forced_offline():
    fake = FakeClaude({"category": "unknown", "root_cause": "", "evidence": [],
                       "confidence": 0, "fix_summary": "", "files_touched": []})
    r = diagnose(LOG, {}, client=fake, use_llm=False)
    assert fake.calls == 0 and "budget" in r.warnings[0].lower()


def test_prompt_version_recorded_on_result():
    assert diagnose(LOG, {}).prompt_version == PROMPT_VERSION


def test_claude_client_uses_breaker_cache_control_and_records_cache_tokens(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "anthropic_api_key", "test-key")
    monkeypatch.setattr(claude_client, "_breaker", CircuitBreaker(2, 60))
    sent = {}

    class Messages:
        def create(self, **kwargs):
            sent.update(kwargs)
            return SimpleNamespace(
                model="m", content=[SimpleNamespace(type="tool_use", input={"ok": True})],
                usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                                      cache_read_input_tokens=7, cache_creation_input_tokens=0))

    client = ClaudeClient()
    client._client = SimpleNamespace(messages=Messages())
    res = client.structured(system="sys", user="u", tool_name="t", schema={})
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert res.cache_read_tokens == 7


def test_claude_client_rejects_calls_while_breaker_open(monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    breaker = CircuitBreaker(1, 60)
    monkeypatch.setattr(claude_client, "_breaker", breaker)

    class Boom:
        def create(self, **_):
            raise RuntimeError("down")

    client = ClaudeClient()
    client._client = SimpleNamespace(messages=Boom())
    with pytest.raises(RuntimeError):
        client.structured(system="s", user="u", tool_name="t", schema={})
    with pytest.raises(LLMUnavailable, match="circuit breaker"):
        client.structured(system="s", user="u", tool_name="t", schema={})


def _diagnosis(repo_id: str, tokens: int):
    s = next(get_session())
    run = PipelineRun(repository_id=repo_id, provider_run_id=str(tokens), conclusion="failure")
    s.add(run)
    s.flush()
    s.add(Diagnosis(pipeline_run_id=run.id, category="x", root_cause="x", confidence=0.5,
                    model="m", input_tokens=tokens, output_tokens=0))
    s.commit()


def test_daily_token_budget_is_per_repo(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "repo_daily_token_budget", 1000)
    a = client.post("/api/repositories", json={"full_name": "o/a"}).json()["id"]
    b = client.post("/api/repositories", json={"full_name": "o/b"}).json()["id"]
    _diagnosis(a, 600)
    _diagnosis(a, 500)
    s = next(get_session())
    assert tokens_used_today(s, a) == 1100 and budget_exhausted(s, a)
    assert not budget_exhausted(s, b)

    monkeypatch.setattr(get_settings(), "repo_daily_token_budget", 0)  # 0 = unlimited
    assert not budget_exhausted(s, a)


def test_metrics_endpoint_exposes_ai_and_http_series(client):
    metrics.record_diagnosis("dependency", "claude-x", 1000, 500, 1200)
    client.post("/api/diagnose-log", json={"log": LOG})
    text = client.get("/metrics").text
    assert 'devpilot_diagnoses_total{category="dependency",model="claude-x"}' in text
    assert 'devpilot_llm_tokens_total{direction="input",model="claude-x"}' in text
    assert "devpilot_llm_cost_usd_total" in text
    assert 'devpilot_http_request_duration_seconds_count{method="POST",route="/api/diagnose-log"' \
        in text


def test_cost_estimate_uses_configured_prices(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "price_input_per_mtok", 2.0)
    monkeypatch.setattr(s, "price_output_per_mtok", 10.0)
    assert metrics.estimate_cost_usd(1_000_000, 500_000) == pytest.approx(7.0)
