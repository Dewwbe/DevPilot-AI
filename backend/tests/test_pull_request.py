import json
import subprocess
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import get_settings
from app.core.db import get_session
from app.models.entities import (
    ApprovalStatus,
    Diagnosis,
    PipelineRun,
    ProposedFix,
    RiskLevel,
)
from app.services.github_app import (
    GitHubAppAuth,
    PullRequestError,
    build_pr_body,
    open_fix_pr,
)


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout


def _git(cwd, *args):
    return _run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd)


@pytest.fixture
def remote(tmp_path, monkeypatch):
    """A local bare repo standing in for github.com/o/r, plus a valid patch for README.md."""
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-b", "main")
    (seed / "README.md").write_text("hello\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "init")
    bare = tmp_path / "gh" / "o" / "r.git"
    bare.parent.mkdir(parents=True)
    _git(tmp_path, "clone", "--bare", str(seed), str(bare))

    (seed / "README.md").write_text("hello\nfixed\n")
    patch = _git(seed, "diff")
    _git(seed, "checkout", "--", ".")

    monkeypatch.setattr(get_settings(), "github_git_base", (tmp_path / "gh").as_uri())
    monkeypatch.setattr(get_settings(), "github_api_base", "https://api.test")
    return SimpleRemote(bare, patch)


class SimpleRemote:
    def __init__(self, bare: Path, patch: str):
        self.bare, self.patch = bare, patch

    def branches(self) -> list[str]:
        return _run(["git", "branch", "--format=%(refname:short)"], self.bare).split()

    def main_sha(self) -> str:
        return _run(["git", "rev-parse", "main"], self.bare).strip()


def _http(captured: dict, status=201):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["json"] = json.loads(request.content)
        return httpx.Response(status, json={"html_url": "https://github.com/o/r/pull/7"})
    return httpx.Client(transport=httpx.MockTransport(handler))


def _open(remote, tmp_path, captured, patch=None, **kw):
    return open_fix_pr(
        repo_full_name="o/r", default_branch="main", fix_id="abcdef123456",
        patch=remote.patch if patch is None else patch, title="DevPilot fix: readme",
        body="body", token="tok_secret", workdir=tmp_path / "work",
        http=_http(captured, **kw))


def test_opens_pr_from_new_branch_and_never_touches_main(remote, tmp_path):
    before = remote.main_sha()
    captured: dict = {}
    url = _open(remote, tmp_path, captured)

    assert url == "https://github.com/o/r/pull/7"
    assert "devpilot/fix-abcdef12" in remote.branches()
    assert remote.main_sha() == before  # default branch untouched
    assert captured["json"]["head"] == "devpilot/fix-abcdef12"
    assert captured["json"]["base"] == "main"
    assert captured["url"] == "https://api.test/repos/o/r/pulls"
    assert captured["auth"] == "Bearer tok_secret"
    assert "fixed" in _run(["git", "show", "devpilot/fix-abcdef12:README.md"], remote.bare)
    assert not (tmp_path / "work").exists()  # workspace cleaned up


def test_bad_patch_is_rejected_before_anything_is_pushed(remote, tmp_path):
    bad = ("--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-this line is not there\n+x\n")
    with pytest.raises(PullRequestError, match="apply"):
        _open(remote, tmp_path, {}, patch=bad)
    assert remote.branches() == ["main"]


def test_empty_and_oversized_patches_rejected(remote, tmp_path):
    with pytest.raises(PullRequestError, match="no patch"):
        _open(remote, tmp_path, {}, patch="  \n")
    with pytest.raises(PullRequestError, match="too large"):
        _open(remote, tmp_path, {}, patch="x" * 300_000)


def test_github_refusal_is_reported(remote, tmp_path):
    with pytest.raises(PullRequestError, match="422"):
        _open(remote, tmp_path, {}, status=422)


def test_installation_token_flow_signs_rs256_jwt():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["jwt"] = request.headers["authorization"].removeprefix("Bearer ")
        return httpx.Response(201, json={"token": "ghs_installation"})

    auth = GitHubAppAuth("12345", pem.replace("\n", "\\n"), "999",  # env-style escaped PEM
                         http=httpx.Client(transport=httpx.MockTransport(handler)),
                         api_base="https://api.test")
    assert auth.installation_token() == "ghs_installation"
    assert seen["path"] == "/app/installations/999/access_tokens"
    claims = jwt.decode(seen["jwt"], key.public_key(), algorithms=["RS256"])
    assert claims["iss"] == "12345" and claims["exp"] - claims["iat"] <= 600


def test_pr_body_contains_review_context():
    body = build_pr_body(root_cause="missing dep", evidence=["E   No module named x"],
                         risk="medium", reviewer="dewmini", comment="checked locally",
                         fix_id="f1")
    for needle in ("missing dep", "No module named x", "medium", "dewmini", "checked locally",
                   "never pushes to the default branch"):
        assert needle in body


def _fix(status: ApprovalStatus, patch="--- a\n+++ b\n", pr_url=None) -> str:
    s = next(get_session())
    run = PipelineRun(repository_id="r1", provider_run_id="1", conclusion="failure")
    s.add(run)
    s.flush()
    d = Diagnosis(pipeline_run_id=run.id, category="x", root_cause="x", confidence=0.8, model="m")
    s.add(d)
    s.flush()
    fix = ProposedFix(diagnosis_id=d.id, summary="s", patch=patch, risk=RiskLevel.low,
                      status=status, decided_by="dewmini", pr_url=pr_url)
    s.add(fix)
    s.commit()
    return fix.id


def test_open_pr_endpoint_guards(client, monkeypatch):
    from app.workers import tasks

    queued: list[str] = []
    monkeypatch.setattr(tasks.open_fix_pr_task, "delay", queued.append)
    s = get_settings()

    assert client.post("/api/fixes/nope/open-pr").status_code == 404
    pending = _fix(ApprovalStatus.pending)
    assert client.post(f"/api/fixes/{pending}/open-pr").status_code == 409  # not approved
    no_patch = _fix(ApprovalStatus.approved, patch="")
    assert client.post(f"/api/fixes/{no_patch}/open-pr").status_code == 422
    done = _fix(ApprovalStatus.approved, pr_url="https://github.com/o/r/pull/1")
    assert client.post(f"/api/fixes/{done}/open-pr").status_code == 409
    ok = _fix(ApprovalStatus.approved)
    assert client.post(f"/api/fixes/{ok}/open-pr").status_code == 503  # App not configured

    for name, value in (("github_app_id", "1"), ("github_app_private_key", "k"),
                        ("github_app_installation_id", "2")):
        monkeypatch.setattr(s, name, value)
    assert client.post(f"/api/fixes/{ok}/open-pr").status_code == 202
    assert queued == [ok]
    actions = [e["action"] for e in client.get("/api/audit").json()]
    assert "fix.pr_requested" in actions


def test_task_records_failure_without_raising(client, monkeypatch):
    from app.models.entities import Repository
    from app.workers import tasks

    s = next(get_session())
    s.add(Repository(id="r1", full_name="o/r"))
    s.commit()
    fix_id = _fix(ApprovalStatus.approved)
    for name, value in (("github_app_id", "1"), ("github_app_private_key", "not-a-key"),
                        ("github_app_installation_id", "2")):
        monkeypatch.setattr(get_settings(), name, value)

    tasks.open_fix_pr_task(fix_id)  # invalid key -> must be caught and audited
    failed = [e for e in client.get("/api/audit").json() if e["action"] == "fix.pr_failed"]
    assert failed and failed[0]["target"] == fix_id
