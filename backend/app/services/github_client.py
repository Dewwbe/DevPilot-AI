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


class GitHubError(RuntimeError):
    """A GitHub API failure with a message that is safe and useful to show in the UI."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _explain(exc: httpx.HTTPStatusError, full_name: str) -> GitHubError:
    code = exc.response.status_code
    has_token = bool(get_settings().github_token)
    if code == 404:
        hint = "" if has_token else " If it is private, set DEVPILOT_GITHUB_TOKEN."
        return GitHubError(404, f"Repository {full_name} was not found on GitHub.{hint}")
    if code in (401, 403):
        remaining = exc.response.headers.get("x-ratelimit-remaining")
        if remaining == "0":
            return GitHubError(429, "GitHub API rate limit reached. Set DEVPILOT_GITHUB_TOKEN "
                                    "(unauthenticated requests are limited to 60 per hour).")
        return GitHubError(403, "GitHub refused the request. Check that DEVPILOT_GITHUB_TOKEN is "
                                "valid and can read this repository's Actions.")
    return GitHubError(502, f"GitHub returned HTTP {code}.")


def lookup_repo(full_name: str) -> dict | None:
    """Repository metadata (default branch etc.), or None if GitHub can't be reached.

    Raises GitHubError for definite answers (not found, forbidden) so the UI can say why.
    """
    try:
        return GitHubClient().get_repo(full_name)
    except httpx.HTTPStatusError as exc:
        raise _explain(exc, full_name) from exc
    except httpx.HTTPError:
        return None  # offline or GitHub outage: connect anyway and let later calls report it


def recent_failed_runs(full_name: str, limit: int = 15) -> list[dict]:
    """Recent failed workflow runs, reduced to the fields the dashboard needs."""
    try:
        runs = GitHubClient().failed_runs(full_name, limit=limit)
    except httpx.HTTPStatusError as exc:
        raise _explain(exc, full_name) from exc
    except httpx.HTTPError as exc:
        raise GitHubError(502, "Could not reach GitHub.") from exc
    return [{
        "id": str(r["id"]), "name": r.get("name") or "workflow",
        "title": r.get("display_title") or r.get("name") or "",
        "branch": r.get("head_branch") or "", "sha": (r.get("head_sha") or "")[:7],
        "url": r.get("html_url") or "", "created_at": r.get("created_at") or "",
        "conclusion": r.get("conclusion") or "failure",
    } for r in runs]


def shallow_clone(full_name: str, dest: Path, branch: str = "main") -> Path:
    """Clone into an isolated workspace. Runs as the unprivileged worker user."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", branch,
         f"https://github.com/{full_name}.git", str(dest)],
        check=True, capture_output=True, timeout=120,
    )
    return dest
