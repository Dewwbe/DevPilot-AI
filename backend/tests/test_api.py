from app.core.db import get_session
from app.models.entities import Diagnosis, PipelineRun, ProposedFix, RiskLevel


def test_health(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}


def test_connect_repository(client):
    r = client.post("/api/repositories", json={"full_name": "octocat/hello-world"})
    assert r.status_code == 201
    assert client.post("/api/repositories",
                       json={"full_name": "octocat/hello-world"}).status_code == 409
    assert client.post("/api/repositories", json={"full_name": "bad name"}).status_code == 422


def test_diagnose_log_endpoint(client):
    r = client.post("/api/diagnose-log", json={"log": "FAILED tests/test_a.py::test_x"})
    assert r.status_code == 200
    assert r.json()["category"] == "test_failure"


def _seed_fix(risk: RiskLevel) -> str:
    s = next(get_session())
    repo_id = "r1"
    run = PipelineRun(repository_id=repo_id, provider_run_id="1", conclusion="failure")
    s.add(run)
    s.flush()
    d = Diagnosis(pipeline_run_id=run.id, category="config", root_cause="x",
                  confidence=0.8, model="fake")
    s.add(d)
    s.flush()
    fix = ProposedFix(diagnosis_id=d.id, summary="edit ci", risk=risk)
    s.add(fix)
    s.commit()
    return fix.id


def test_high_risk_fix_requires_justification(client):
    fix_id = _seed_fix(RiskLevel.high)
    body = {"decision": "approved", "reviewer": "dewmini"}
    assert client.post(f"/api/fixes/{fix_id}/decision", json=body).status_code == 422
    body["comment"] = "Verified workflow change locally"
    assert client.post(f"/api/fixes/{fix_id}/decision", json=body).status_code == 200
    assert client.post(f"/api/fixes/{fix_id}/decision", json=body).status_code == 409
    actions = [e["action"] for e in client.get("/api/audit").json()]
    assert "fix.approved" in actions
