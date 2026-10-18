"""Minimal GitHub REST client (read-only in Phase 1).

Phase 1: clone repo, list failed workflow runs, download job logs.
Phase 3: open a branch + pull request for an *approved* fix only.
DevPilot never pushes to the default branch.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import httpx

from app.core.config import get_settings

API = "https://api.github.com"


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        token = token if token is not None else get_settings().github_token
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(base_url=API, headers=headers, timeout=30,
                                  follow_redirects=True)

    def get_repo(self, full_name: str) -> dict:
        r = self._http.get(f"/repos/{full_name}")
        r.raise_for_status()
        return r.json()

    def failed_runs(self, full_name: str, limit: int = 10) -> list[dict]:
        r = self._http.get(f"/repos/{full_name}/actions/runs",
                           params={"status": "failure", "per_page": limit})
        r.raise_for_status()
        return r.json().get("workflow_runs", [])

    def failed_jobs(self, full_name: str, run_id: int) -> list[dict]:
        r = self._http.get(f"/repos/{full_name}/actions/runs/{run_id}/jobs")
        r.raise_for_status()
        return [j for j in r.json().get("jobs", []) if j.get("conclusion") == "failure"]

    def job_log(self, full_name: str, job_id: int) -> str:
        r = self._http.get(f"/repos/{full_name}/actions/jobs/{job_id}/logs")
        r.raise_for_status()
        return r.text


def shallow_clone(full_name: str, dest: Path, branch: str = "main") -> Path:
    """Clone into an isolated workspace. Runs as the unprivileged worker user."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", branch,
         f"https://github.com/{full_name}.git", str(dest)],
        check=True, capture_output=True, timeout=120,
    )
    return dest
