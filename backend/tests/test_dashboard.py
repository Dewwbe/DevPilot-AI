import pytest

from app.core.db import get_session
from app.models.entities import (
    Analysis,
    ApprovalStatus,
    AuditEvent,
    Diagnosis,
    PipelineRun,
    ProposedFix,
    RiskLevel,
)
from app.schemas.api import RepositoryCreate, normalize_repo
from app.services.github_client import GitHubError

LOG = "E   ModuleNotFoundError: No module named 'requests'\nProcess completed with exit code 1."


# ---------- repository links ----------

@pytest.mark.parametrize("raw", [
    "octocat/hello-world",
    "https://github.com/octocat/hello-world",
    "https://github.com/octocat/hello-world/",
    "https://github.com/octocat/hello-world.git",
    "http://www.github.com/octocat/hello-world/actions/runs/123",
    "github.com/octocat/hello-world",
    "git@github.com:octocat/hello-world.git",
    "  https://github.com/octocat/hello-world?tab=readme  ",
])
def test_repository_links_are_normalised(raw):
    assert normalize_repo(raw) == "octocat/hello-world"
    assert RepositoryCreate(full_name=raw).full_name == "octocat/hello-world"


def test_connect_by_url_and_reject_garbage(client):
    r = client.post("/api/repositories", json={"full_name": "https://github.com/octocat/hello"})
    assert r.status_code == 201 and r.json()["full_name"] == "octocat/hello"
    assert client.post("/api/repositories", json={"full_name": "https://gitlab.com/a/b"}
                       ).status_code == 422
    assert client.post("/api/repositories", json={"full_name": "just a sentence"}
                       ).status_code == 422


def test_connect_uses_github_metadata_and_blocks_duplicates_ignoring_case(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.repositories.lookup_repo", lambda n: {
        "full_name": "Octocat/Hello-World", "default_branch": "develop"})
    r = client.post("/api/repositories", json={"full_name": "octocat/hello-world"})
    assert r.json()["full_name"] == "Octocat/Hello-World"  # canonical capitalisation
    assert r.json()["default_branch"] == "develop"
    assert client.post("/api/repositories", json={"full_name": "OCTOCAT/hello-world"}
                       ).status_code == 409


def test_connect_reports_why_github_refused(client, monkeypatch):
    def refuse(name):
        raise GitHubError(404, f"Repository {name} was not found on GitHub.")

    monkeypatch.setattr("app.api.routes.repositories.lookup_repo", refuse)
    r = client.post("/api/repositories", json={"full_name": "nobody/nothing"})
    assert r.status_code == 404 and "not found" in r.json()["detail"]
    assert client.get("/api/repositories").json() == []


# ---------- failed runs ----------

RUNS = [
    {"id": "11", "name": "CI", "title": "Fix tests", "branch": "main", "sha": "abc1234",
     "url": "https://github.com/o/r/actions/runs/11", "created_at": "2026-01-01T00:00:00Z",
     "conclusion": "failure"},
    {"id": "12", "name": "CI", "title": "Add feature", "branch": "dev", "sha": "def5678",
     "url": "https://github.com/o/r/actions/runs/12", "created_at": "2026-01-02T00:00:00Z",
     "conclusion": "failure"},
]


def _connect(client) -> str:
    return client.post("/api/repositories", json={"full_name": "o/r"}).json()["id"]


def test_list_runs_marks_diagnosed_in_progress_and_failed(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.repositories.recent_failed_runs", lambda n, limit: RUNS)
    repo_id = _connect(client)
    s = next(get_session())
    done = PipelineRun(repository_id=repo_id, provider_run_id="11", conclusion="failure")
    s.add(done)
    s.flush()
    diag = Diagnosis(pipeline_run_id=done.id, category="dependency", root_cause="x",
                     confidence=0.5, model="m")
    s.add(diag)
    s.commit()
    diag_id = diag.id

    runs = {r["id"]: r for r in client.get(f"/api/repositories/{repo_id}/runs").json()}
    assert runs["11"]["diagnosis_id"] == diag_id and not runs["11"]["diagnosing"]
    assert runs["12"]["diagnosis_id"] is None and not runs["12"]["diagnosing"]

    s = next(get_session())
    queued = PipelineRun(repository_id=repo_id, provider_run_id="12", conclusion="failure")
    s.add(queued)
    s.commit()
    runs = {r["id"]: r for r in client.get(f"/api/repositories/{repo_id}/runs").json()}
    assert runs["12"]["diagnosing"] is True

    s = next(get_session())
    s.add(AuditEvent(actor="system", action="diagnosis.failed", target=queued.id,
                     detail={"error": "404 Not Found"}))
    s.commit()
    runs = {r["id"]: r for r in client.get(f"/api/repositories/{repo_id}/runs").json()}
    assert runs["12"]["diagnosing"] is False and "404" in runs["12"]["error"]


def test_list_runs_surfaces_github_errors_and_404(client, monkeypatch):
    repo_id = _connect(client)

    def limited(name, limit):
        raise GitHubError(429, "GitHub API rate limit reached.")

    monkeypatch.setattr("app.api.routes.repositories.recent_failed_runs", limited)
    r = client.get(f"/api/repositories/{repo_id}/runs")
    assert r.status_code == 429 and "rate limit" in r.json()["detail"]
    assert client.get("/api/repositories/nope/runs").status_code == 404


def test_diagnose_run_is_idempotent_and_retries_failures(client, monkeypatch):
    from app.workers import tasks

    queued: list[str] = []
    monkeypatch.setattr(tasks.diagnose_run_task, "delay", queued.append)
    repo_id = _connect(client)

    first = client.post(f"/api/repositories/{repo_id}/runs/11/diagnose").json()
    assert first["status"] == "queued" and len(queued) == 1
    again = client.post(f"/api/repositories/{repo_id}/runs/11/diagnose").json()
    assert again["pipeline_run_id"] == first["pipeline_run_id"]  # same run, not a duplicate row
    assert len(queued) == 2  # no diagnosis yet, so it is (re)queued, i.e. retry after a failure

    s = next(get_session())
    assert s.query(PipelineRun).count() == 1
    s.add(Diagnosis(pipeline_run_id=first["pipeline_run_id"], category="x", root_cause="x",
                    confidence=0.5, model="m"))
    s.commit()
    done = client.post(f"/api/repositories/{repo_id}/runs/11/diagnose").json()
    assert done["status"] == "done" and done["diagnosis_id"]
    assert len(queued) == 2  # nothing new queued once a diagnosis exists


def test_repository_list_shows_counts_and_analysis_status(client):
    repo_id = _connect(client)
    s = next(get_session())
    s.add(Analysis(repository_id=repo_id, status="completed", profile={}))
    run = PipelineRun(repository_id=repo_id, provider_run_id="1", conclusion="failure")
    s.add(run)
    s.flush()
    s.add(Diagnosis(pipeline_run_id=run.id, category="x", root_cause="x", confidence=0.5,
                    model="m"))
    s.commit()
    row = client.get("/api/repositories").json()[0]
    assert row["diagnosis_count"] == 1 and row["analysis_status"] == "completed"


# ---------- history ----------

def test_pasted_diagnosis_is_saved_with_its_origin_and_excerpt(client):
    r = client.post("/api/diagnose-log", json={"log": LOG}).json()
    assert r["id"]
    detail = client.get(f"/api/diagnoses/{r['id']}").json()
    assert detail["source"] == "pasted" and detail["repository"] is None
    assert detail["created_by"] == "anonymous"
    assert "No module named" in detail["log_excerpt"]
    assert [d["id"] for d in client.get("/api/diagnoses").json()] == [r["id"]]
    assert "diagnosis.pasted" in [e["action"] for e in client.get("/api/audit").json()]


def test_history_redacts_secrets_in_the_stored_excerpt(client):
    r = client.post("/api/diagnose-log", json={
        "log": "password=hunter2supersecret\nE   boom\nexit code 1"}).json()
    assert "hunter2supersecret" not in client.get(f"/api/diagnoses/{r['id']}").json()["log_excerpt"]


def test_history_filters(client):
    repo_id = _connect(client)
    s = next(get_session())
    run = PipelineRun(repository_id=repo_id, provider_run_id="9", conclusion="failure")
    s.add(run)
    s.flush()
    d1 = Diagnosis(pipeline_run_id=run.id, category="dependency", root_cause="a",
                   confidence=0.9, model="claude", source="run")
    d2 = Diagnosis(pipeline_run_id=None, category="test_failure", root_cause="b",
                   confidence=0.4, model="heuristic", source="pasted")
    s.add_all([d1, d2])
    s.flush()
    s.add(ProposedFix(diagnosis_id=d1.id, summary="s", risk=RiskLevel.low,
                      status=ApprovalStatus.approved))
    s.commit()

    def ids(**params):
        return {d["category"] for d in client.get("/api/diagnoses", params=params).json()}

    assert ids() == {"dependency", "test_failure"}
    assert ids(repository="o/r") == {"dependency"}
    assert ids(category="test_failure") == {"test_failure"}
    assert ids(source="pasted") == {"test_failure"}
    assert ids(status="approved") == {"dependency"}
    assert client.get("/api/diagnoses", params={"status": "bogus"}).status_code == 422
    assert client.get("/api/diagnoses/missing").status_code == 404
    assert len(client.get("/api/diagnoses", params={"limit": 1}).json()) == 1


def test_open_pr_refused_for_pasted_diagnoses(client, monkeypatch):
    from app.core.config import get_settings

    for k, v in (("github_app_id", "1"), ("github_app_private_key", "k"),
                 ("github_app_installation_id", "2")):
        monkeypatch.setattr(get_settings(), k, v)
    s = next(get_session())
    d = Diagnosis(pipeline_run_id=None, category="x", root_cause="x", confidence=0.5,
                  model="m", source="pasted")
    s.add(d)
    s.flush()
    fix = ProposedFix(diagnosis_id=d.id, summary="s", patch="--- a\n+++ b\n",
                      risk=RiskLevel.low, status=ApprovalStatus.approved)
    s.add(fix)
    s.commit()
    r = client.post(f"/api/fixes/{fix.id}/open-pr")
    assert r.status_code == 422 and "no repository" in r.json()["detail"]


# ---------- dashboard stats ----------

def test_stats_empty_database(client):
    s = client.get("/api/stats").json()
    assert s["diagnoses_total"] == 0 and s["approval_rate"] is None
    assert s["avg_confidence"] is None and len(s["per_day"]) == 14
    assert all(d["count"] == 0 for d in s["per_day"])


def test_stats_numbers(client):
    _connect(client)
    s = next(get_session())
    diags = [Diagnosis(category=c, root_cause="x", confidence=conf, model=m,
                       input_tokens=1000, output_tokens=500, source="pasted")
             for c, conf, m in [("dependency", 0.8, "claude"), ("dependency", 0.6, "claude"),
                                ("test_failure", 0.3, "heuristic")]]
    s.add_all(diags)
    s.flush()
    for d, st in zip(diags, (ApprovalStatus.approved, ApprovalStatus.approved,
                             ApprovalStatus.rejected), strict=True):
        s.add(ProposedFix(diagnosis_id=d.id, summary="s", risk=RiskLevel.low, status=st))
    s.add(ProposedFix(diagnosis_id=diags[0].id, summary="p", risk=RiskLevel.low))  # pending
    s.add(AuditEvent(actor="system", action="fix.pr_opened", target="f", detail={}))
    s.commit()

    st = client.get("/api/stats").json()
    assert st["repositories"] == 1 and st["diagnoses_total"] == 3 and st["diagnoses_7d"] == 3
    assert st["approved_fixes"] == 2 and st["rejected_fixes"] == 1 and st["pending_fixes"] == 1
    assert st["approval_rate"] == pytest.approx(2 / 3)
    assert st["avg_confidence"] == pytest.approx((0.8 + 0.6 + 0.3) / 3)
    assert st["heuristic_share"] == pytest.approx(1 / 3)
    assert st["prs_opened"] == 1 and st["tokens_7d"] == 4500
    assert {c["category"]: c["count"] for c in st["by_category"]} == {
        "dependency": 2, "test_failure": 1}
    assert sum(d["count"] for d in st["per_day"]) == 3
    assert st["per_day"][-1]["count"] == 3  # all created today
