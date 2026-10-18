"""Check runner: run lint/test/audit tools on a cloned repo inside throwaway containers.

Untrusted code is executed here, so every check runs in its own container that is:
non-root, read-only root fs, all capabilities dropped, no-new-privileges, memory/CPU/pid limited,
time-limited, and removed afterwards. The clone is mounted read-only; the check copies it into a
tmpfs before installing dependencies. See docs/SAFETY.md (check-runner sandbox).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import get_settings

OUTPUT_TAIL_CHARS = 6000


@dataclass(frozen=True)
class CheckSpec:
    name: str
    command: str  # run with sh -c inside a writable copy of the repo (cwd = /tmp/src)


def plan_checks(workdir: Path) -> list[CheckSpec]:
    """Pick checks from the files present in the repository."""
    has = lambda name: (workdir / name).exists()  # noqa: E731
    checks: list[CheckSpec] = []

    py_project = has("pyproject.toml") or has("requirements.txt") or has("setup.py")
    if py_project:
        install = (
            "python -m venv /tmp/venv && . /tmp/venv/bin/activate && "
            + ("pip install -q -r requirements.txt"
               if has("requirements.txt") else 'pip install -q -e ".[dev]" || pip install -q -e .')
        )
        checks.append(CheckSpec("ruff", "ruff check ."))
        checks.append(CheckSpec("pytest", f"{install} && pip install -q pytest && pytest -q"))
        audit = "pip-audit -r requirements.txt" if has("requirements.txt") else "pip-audit ."
        checks.append(CheckSpec("pip-audit", audit))

    if has("package.json"):
        checks.append(CheckSpec(
            "eslint",
            "(npm ci --ignore-scripts --no-audit --no-fund || npm install --ignore-scripts "
            "--no-audit --no-fund) && npm run lint --if-present",
        ))
    return checks


def _docker_client() -> Any:
    import docker

    return docker.from_env()


def _run_one(client: Any, spec: CheckSpec, workspace_name: str) -> dict:
    from docker.types import Mount

    s = get_settings()
    script = f'cp -r "$SRC" /tmp/src && cd /tmp/src && {spec.command}'
    started = time.monotonic()
    container = client.containers.run(
        s.runner_image,
        ["sh", "-c", script],
        detach=True,
        environment={"SRC": f"/workspaces/{workspace_name}", "HOME": "/tmp",
                     "PIP_DISABLE_PIP_VERSION_CHECK": "1", "CI": "true"},
        mounts=[Mount(target="/workspaces", source=s.runner_workspace_volume,
                      type="volume", read_only=True)],
        working_dir="/tmp",
        tmpfs={"/tmp": "rw,exec,size=2g"},
        read_only=True,
        cap_drop=["ALL"],
        security_opt=["no-new-privileges"],
        pids_limit=512,
        mem_limit=s.runner_memory,
        nano_cpus=int(s.runner_cpus * 1_000_000_000),
        network_mode=s.runner_network,
        labels={"devpilot.role": "check-runner"},
    )
    timed_out = False
    exit_code = -1
    try:
        try:
            exit_code = int(container.wait(timeout=s.runner_timeout_s).get("StatusCode", -1))
        except Exception:  # noqa: BLE001  (timeout or connection error from docker SDK)
            timed_out = True
            container.kill()
        output = container.logs(tail=200).decode("utf-8", errors="replace")
    finally:
        container.remove(force=True)
    return {
        "name": spec.name,
        "passed": exit_code == 0 and not timed_out,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_s": round(time.monotonic() - started, 1),
        "output_tail": output[-OUTPUT_TAIL_CHARS:],
    }


def run_checks(workdir: Path, client: Any | None = None) -> list[dict]:
    """Run every applicable check; one failing check never stops the others."""
    specs = plan_checks(workdir)
    if not specs:
        return []
    client = client or _docker_client()
    results = []
    for spec in specs:
        try:
            results.append(_run_one(client, spec, workdir.name))
        except Exception as exc:  # noqa: BLE001
            results.append({"name": spec.name, "passed": False, "exit_code": -1,
                            "timed_out": False, "duration_s": 0.0,
                            "output_tail": f"runner error: {exc}"})
    return results
