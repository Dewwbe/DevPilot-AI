import json

from app.services.deployment_assistant import (
    generate,
    template_dockerfile,
    template_manifest,
    validate_dockerfile,
    validate_manifest,
)

PY = {"primary_language": "Python", "manifests": ["requirements.txt"]}


def fake_runner(dockerfile_issues=None, manifest_invalid=False):
    """Stands in for hadolint / kubeconform."""
    def run(argv, stdin):
        if argv[0] == "hadolint":
            bad = dockerfile_issues(stdin) if callable(dockerfile_issues) else dockerfile_issues
            out = json.dumps(bad or [])
            return (1 if bad else 0), out
        res = [{"kind": "Deployment", "name": "x",
                "status": "statusInvalid" if manifest_invalid else "statusValid",
                "msg": "bad field"}]
        return (1 if manifest_invalid else 0), json.dumps({"resources": res})
    return run


class ScriptedClaude:
    def __init__(self, *responses):
        self.responses, self.prompts = list(responses), []

    def structured(self, *, user, **_):
        from app.services.claude_client import LLMResult

        self.prompts.append(user)
        return LLMResult(data=self.responses.pop(0), model="fake", input_tokens=1,
                         output_tokens=1, latency_ms=1)


def test_validate_dockerfile_flags_warnings_but_not_info():
    out = [{"level": "info", "code": "DL3059", "message": "x", "line": 1},
           {"level": "warning", "code": "DL3008", "message": "pin versions", "line": 3}]
    v = validate_dockerfile("FROM x", fake_runner(out))
    assert not v.passed and v.issues == ["line 3: DL3008 pin versions"]


def test_missing_validator_fails_closed():
    def missing(argv, stdin):
        raise FileNotFoundError(argv[0])

    assert not validate_dockerfile("FROM x", missing).passed
    assert not validate_manifest("kind: Pod", missing).passed


def test_invalid_manifest_reported():
    v = validate_manifest("x", fake_runner(manifest_invalid=True))
    assert not v.passed and "Deployment/x: bad field" in v.issues[0]


def test_templates_cover_python_and_node_and_skip_unknown():
    assert "USER app" in template_dockerfile(PY)
    assert "npm ci" in template_dockerfile({"primary_language": "TypeScript", "manifests": []})
    assert template_dockerfile({"primary_language": "Go"}) is None
    assert "runAsNonRoot: true" in template_manifest(PY, "Owner/My Repo")
    assert "name: my-repo" in template_manifest(PY, "Owner/My Repo")


def test_offline_templates_are_shown_only_after_validation():
    arts = generate(PY, "o/app", use_llm=False, runner=fake_runner())
    assert {a.filename for a in arts} == {"Dockerfile", "k8s.yaml"}
    assert all(a.source == "template" and a.content for a in arts)


def test_content_withheld_when_validation_fails():
    issue = [{"level": "error", "code": "DL1", "message": "m", "line": 1}]
    arts = generate(PY, "o/app", kind="dockerfile", use_llm=False, runner=fake_runner(issue))
    assert arts[0].content is None and not arts[0].validation.passed


def test_claude_output_is_repaired_once_using_validator_findings():
    good = "FROM python:3.12-slim\nUSER app\n"
    claude = ScriptedClaude(
        {"dockerfile": "FROM python\n", "k8s_manifest": "", "notes": ""},
        {"dockerfile": good, "k8s_manifest": "", "notes": ""},
    )

    def only_latest_tag_fails(stdin):
        return [{"level": "warning", "code": "DL3006", "message": "tag the image", "line": 1}] \
            if stdin.startswith("FROM python\n") else None

    arts = generate(PY, "o/app", kind="dockerfile", client=claude,
                    runner=fake_runner(only_latest_tag_fails))
    assert arts[0].source == "claude" and arts[0].content == good
    assert "DL3006" in claude.prompts[1]  # validator findings were fed back


def test_falls_back_to_template_when_claude_keeps_failing_or_errors():
    class Down:
        def structured(self, **_):
            raise RuntimeError("overloaded")

    arts = generate(PY, "o/app", kind="dockerfile", client=Down(), runner=fake_runner())
    assert arts[0].source == "template" and arts[0].content


def test_unsupported_language_returns_nothing_to_show():
    arts = generate({"primary_language": "Go"}, "o/app", kind="dockerfile", use_llm=False,
                    runner=fake_runner())
    assert arts[0].content is None and arts[0].source == "none"


def test_endpoint_requires_analysis_then_returns_validated_files(client, monkeypatch):
    from app.core.db import get_session
    from app.models.entities import Analysis
    from app.services import deployment_assistant as da

    repo_id = client.post("/api/repositories", json={"full_name": "o/app"}).json()["id"]
    assert client.post(f"/api/repositories/{repo_id}/deployment-assist",
                       json={"kind": "both"}).status_code == 409

    s = next(get_session())
    s.add(Analysis(repository_id=repo_id, status="completed", profile=PY))
    s.commit()
    real_generate = da.generate
    monkeypatch.setattr(da, "generate", lambda *a, **k: real_generate(
        *a, use_llm=False, runner=fake_runner(), **k))
    r = client.post(f"/api/repositories/{repo_id}/deployment-assist", json={"kind": "both"})
    assert r.status_code == 200
    files = {a["filename"]: a for a in r.json()["artifacts"]}
    assert files["Dockerfile"]["validation"]["passed"] and files["Dockerfile"]["content"]
    assert "deployment.generated" in [e["action"] for e in client.get("/api/audit").json()]
    assert client.post(f"/api/repositories/{repo_id}/deployment-assist",
                       json={"kind": "nope"}).status_code == 422
