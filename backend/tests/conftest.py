import os

os.environ["DEVPILOT_ENV"] = "test"
os.environ["DEVPILOT_DATABASE_URL"] = "sqlite:///./test.db"
os.environ["DEVPILOT_ANTHROPIC_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.services.claude_client import LLMResult  # noqa: E402


class FakeClaude:
    """Deterministic stand-in for the Claude API used in unit tests and evals."""

    def __init__(self, data: dict):
        self.data = data
        self.calls = 0

    def structured(self, **_kwargs) -> LLMResult:
        self.calls += 1
        return LLMResult(data=self.data, model="fake", input_tokens=100,
                         output_tokens=50, latency_ms=1)


@pytest.fixture
def client():
    from app.core.db import Base, get_engine, init_db
    from app.main import app

    init_db()
    Base.metadata.drop_all(get_engine())  # clean slate per test
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _no_github_lookup(monkeypatch):
    """Never hit github.com from unit tests: pretend GitHub is unreachable (connect falls back)."""
    monkeypatch.setattr("app.api.routes.repositories.lookup_repo", lambda full_name: None)
