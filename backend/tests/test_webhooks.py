import hashlib
import hmac
import json

import pytest

from app.api.routes.webhooks import verify_signature
from app.core.config import get_settings
from app.models.entities import PipelineRun

SECRET = "s3cret"


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _payload(conclusion="failure", action="completed", repo="octocat/demo", run_id=42) -> bytes:
    return json.dumps({
        "action": action,
        "workflow_run": {"id": run_id, "conclusion": conclusion, "name": "CI", "head_sha": "abc"},
        "repository": {"full_name": repo},
    }).encode()


@pytest.fixture
def queued(monkeypatch):
    """Enable the webhook and capture queued diagnoses instead of running them."""
    monkeypatch.setattr(get_settings(), "github_webhook_secret", SECRET)
    calls: list[str] = []
    from app.workers import tasks

    monkeypatch.setattr(tasks.diagnose_run_task, "delay", lambda run_id: calls.append(run_id))
    return calls


def _post(client, body: bytes, event="workflow_run", sig: str | None = None):
    headers = {"X-GitHub-Event": event, "Content-Type": "application/json",
               "X-Hub-Signature-256": sig if sig is not None else _sign(body)}
    return client.post("/api/webhooks/github", content=body, headers=headers)


def test_verify_signature():
    body = b"{}"
    assert verify_signature(SECRET, body, _sign(body))
    assert not verify_signature(SECRET, body, _sign(body, "other"))
    assert not verify_signature(SECRET, body, None)
    assert not verify_signature("", body, _sign(body, ""))  # empty secret never validates


def test_disabled_without_secret(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "github_webhook_secret", "")
    assert _post(client, b"{}").status_code == 503


def test_rejects_bad_signature(client, queued):
    r = _post(client, _payload(), sig="sha256=deadbeef")
    assert r.status_code == 401
    assert queued == []


def test_ping(client, queued):
    assert _post(client, b"{}", event="ping").json() == {"status": "pong"}


def test_failed_run_queues_diagnosis_once(client, queued):
    client.post("/api/repositories", json={"full_name": "octocat/demo"})
    r = _post(client, _payload())
    assert r.status_code == 202 and r.json()["status"] == "queued"
    assert len(queued) == 1

    # GitHub redelivers: must not diagnose the same run twice.
    again = _post(client, _payload())
    assert again.json()["reason"] == "already processed"
    assert len(queued) == 1

    from app.core.db import get_session

    assert next(get_session()).query(PipelineRun).count() == 1
    actions = [e["action"] for e in client.get("/api/audit").json()]
    assert "webhook.workflow_run_failed" in actions


def test_ignores_success_unconnected_and_other_events(client, queued):
    client.post("/api/repositories", json={"full_name": "octocat/demo"})
    assert _post(client, _payload(conclusion="success")).json()["status"] == "ignored"
    assert _post(client, _payload(action="requested")).json()["status"] == "ignored"
    unconnected = _post(client, _payload(repo="someone/else")).json()
    assert unconnected["reason"] == "repository not connected"
    assert _post(client, b"{}", event="push").json()["status"] == "ignored"
    assert queued == []


def test_diagnosis_task_records_failure_when_github_fails(client, monkeypatch):
    from app.core.db import get_session
    from app.workers import tasks

    client.post("/api/repositories", json={"full_name": "octocat/demo"})
    repo_id = client.get("/api/repositories").json()[0]["id"]
    session = next(get_session())
    run = PipelineRun(repository_id=repo_id, provider_run_id="5", conclusion="failure")
    session.add(run)
    session.commit()

    class BrokenGitHub:
        def failed_jobs(self, *_):
            raise RuntimeError("404 Not Found")

    monkeypatch.setattr(tasks, "GitHubClient", BrokenGitHub)
    tasks.diagnose_run_task(run.id)  # must not raise

    events = client.get("/api/audit").json()
    failed = [e for e in events if e["action"] == "diagnosis.failed"]
    assert failed and "404" in failed[0]["detail"]["error"]


def test_malformed_payload(client, queued):
    assert _post(client, b'{"workflow_run": {}}').status_code == 400


def test_log_download_failures_get_actionable_messages():
    import httpx

    from app.workers.tasks import _friendly

    def err(code):
        req = httpx.Request("GET", "https://api.github.com/x")
        resp = httpx.Response(code, request=req)
        return httpx.HTTPStatusError("boom", request=req, response=resp)

    assert "DEVPILOT_GITHUB_TOKEN" in _friendly(err(403))
    assert "DEVPILOT_GITHUB_TOKEN" in _friendly(err(401))
    assert "could not find" in _friendly(err(404))
    assert "HTTP 502" in _friendly(err(502))
    assert _friendly(RuntimeError("plain")) == "plain"
