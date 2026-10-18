from pathlib import Path

from app.services.check_runner import plan_checks, run_checks


class FakeContainer:
    def __init__(self, status: int, out: bytes = b"ok", hang: bool = False):
        self.status, self.out, self.hang = status, out, hang
        self.killed = self.removed = False

    def wait(self, timeout=None):
        if self.hang:
            raise TimeoutError("timed out")
        return {"StatusCode": self.status}

    def kill(self):
        self.killed = True

    def logs(self, tail=200):
        return self.out

    def remove(self, force=False):
        self.removed = True


class FakeDocker:
    """Records container run kwargs; exit codes come from the queue."""

    def __init__(self, containers):
        self._queue = list(containers)
        self.runs: list[dict] = []
        self.containers = self

    def run(self, image, command, **kwargs):
        self.runs.append({"image": image, "command": command, **kwargs})
        return self._queue.pop(0)


def _touch(tmp_path: Path, *names: str) -> Path:
    for n in names:
        (tmp_path / n).write_text("x")
    return tmp_path


def test_plan_python_and_node(tmp_path):
    names = [c.name for c in plan_checks(_touch(tmp_path, "pyproject.toml", "package.json"))]
    assert names == ["ruff", "pytest", "pip-audit", "eslint"]


def test_plan_empty_repo(tmp_path):
    assert plan_checks(tmp_path) == []


def test_plan_prefers_requirements_for_audit(tmp_path):
    specs = {c.name: c.command for c in plan_checks(_touch(tmp_path, "requirements.txt"))}
    assert specs["pip-audit"] == "pip-audit -r requirements.txt"


def test_run_checks_sandbox_flags_and_results(tmp_path):
    repo = _touch(tmp_path, "pyproject.toml")
    docker = FakeDocker([FakeContainer(0), FakeContainer(1, b"FAILED test_x"), FakeContainer(0)])
    results = run_checks(repo, client=docker)

    assert [r["name"] for r in results] == ["ruff", "pytest", "pip-audit"]
    assert [r["passed"] for r in results] == [True, False, True]
    assert "FAILED test_x" in results[1]["output_tail"]

    for run in docker.runs:  # every check is sandboxed identically
        assert run["cap_drop"] == ["ALL"]
        assert run["security_opt"] == ["no-new-privileges"]
        assert run["read_only"] is True
        assert run["pids_limit"] > 0 and run["mem_limit"]
        assert run["mounts"][0]["ReadOnly"] is True
    assert docker._queue == []


def test_timeout_kills_and_removes_container(tmp_path):
    repo = _touch(tmp_path, "pyproject.toml")
    hung = FakeContainer(0, hang=True)
    docker = FakeDocker([hung, FakeContainer(0), FakeContainer(0)])
    results = run_checks(repo, client=docker)
    assert results[0]["timed_out"] and not results[0]["passed"]
    assert hung.killed and hung.removed


def test_docker_error_is_reported_not_raised(tmp_path):
    class Broken:
        containers = None

        def __init__(self):
            self.containers = self

        def run(self, *a, **k):
            raise RuntimeError("no docker socket")

    results = run_checks(_touch(tmp_path, "pyproject.toml"), client=Broken())
    assert all(not r["passed"] and "no docker socket" in r["output_tail"] for r in results)
