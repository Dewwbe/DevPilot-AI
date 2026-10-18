import json

from app.services.repo_analyzer import analyze_repository


def test_detects_stack(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print('hi')")
    (tmp_path / "web.ts").write_text("export {}")
    (tmp_path / "requirements.txt").write_text("fastapi==0.115.0\nrequests\n")
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "^18"}}))
    (tmp_path / "Dockerfile").write_text("FROM python:3.12")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("on: push")

    p = analyze_repository(tmp_path)
    assert p.primary_language in {"Python", "TypeScript"}
    assert "FastAPI" in p.frameworks and "React" in p.frameworks
    assert p.has_dockerfile
    assert p.ci_workflows == [".github/workflows/ci.yml"]
    assert any("requests" in f for f in p.findings)  # unpinned dependency flagged
