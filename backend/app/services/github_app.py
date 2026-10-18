"""Open a pull request for an *approved* fix through a GitHub App (Phase 3).

Guardrails:
- The App needs only Contents: write and Pull requests: write (plus the default Metadata: read).
- DevPilot never pushes to the default branch: changes go to a new `devpilot/fix-<id>` branch,
  never forced, and the PR is opened for a human to review and merge.
- The patch must apply cleanly (`git apply --check`) before anything is committed or pushed.
- The installation token is short-lived and handed to git through the environment, never put in
  a URL or command line, and is scrubbed from any error text.
"""
from __future__ import annotations

import base64
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import httpx
import jwt

from app.core.config import get_settings

MAX_PATCH_BYTES = 200_000
BRANCH_PREFIX = "devpilot/fix-"
GIT_AUTHOR = ("DevPilot AI", "devpilot-ai@users.noreply.github.com")


class PullRequestError(RuntimeError):
    pass


def _force_rmtree(path: Path) -> None:
    """rmtree that also removes read-only files (git object files on Windows)."""
    def _retry(func, p, *_exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_retry)
    else:
        shutil.rmtree(path, onerror=_retry)


def app_configured() -> bool:
    s = get_settings()
    return bool(s.github_app_id and s.github_app_private_key and s.github_app_installation_id)


class GitHubAppAuth:
    """Exchanges the App's private key for a short-lived installation access token."""

    def __init__(self, app_id: str, private_key: str, installation_id: str,
                 http: httpx.Client | None = None, api_base: str | None = None) -> None:
        self.app_id, self.installation_id = app_id, installation_id
        self._key = private_key.replace("\\n", "\n")  # allow single-line PEMs in env files
        self._api = (api_base or get_settings().github_api_base).rstrip("/")
        self._http = http or httpx.Client(timeout=30)

    def app_jwt(self) -> str:
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 540, "iss": self.app_id}  # max 10 minutes
        return jwt.encode(payload, self._key, algorithm="RS256")

    def installation_token(self) -> str:
        r = self._http.post(
            f"{self._api}/app/installations/{self.installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {self.app_jwt()}",
                     "Accept": "application/vnd.github+json"},
        )
        r.raise_for_status()
        return r.json()["token"]


def _git(args: list[str], cwd: Path, token: str, stdin: str | None = None) -> str:
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    env = {
        **{k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if k in os.environ},
        "HOME": str(cwd.parent),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
    }
    proc = subprocess.run(["git", *args], cwd=cwd, env=env, input=stdin, text=True,
                          capture_output=True, timeout=120)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).replace(token, "***").replace(basic, "***")
        raise PullRequestError(f"git {args[0]} failed: {detail.strip()[:500]}")
    return proc.stdout


def open_fix_pr(*, repo_full_name: str, default_branch: str, fix_id: str, patch: str,
                title: str, body: str, token: str, workdir: Path,
                http: httpx.Client | None = None) -> str:
    """Clone, apply the patch on a new branch, push it and open the PR. Returns the PR URL."""
    s = get_settings()
    if not patch.strip():
        raise PullRequestError("Fix has no patch to apply")
    if len(patch.encode()) > MAX_PATCH_BYTES:
        raise PullRequestError("Patch is too large to open automatically")

    branch = f"{BRANCH_PREFIX}{fix_id[:8]}"
    if branch == default_branch:  # defensive: the prefix makes this impossible today
        raise PullRequestError("Refusing to push to the default branch")

    repo_dir = workdir / "repo"
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        _git(["clone", "--depth", "1", "--branch", default_branch,
              f"{s.github_git_base.rstrip('/')}/{repo_full_name}.git", "repo"], workdir, token)
        _git(["apply", "--check", "--whitespace=nowarn", "-"], repo_dir, token, stdin=patch)
        _git(["checkout", "-b", branch], repo_dir, token)
        _git(["apply", "--whitespace=nowarn", "-"], repo_dir, token, stdin=patch)
        _git(["add", "-A"], repo_dir, token)
        if not _git(["status", "--porcelain"], repo_dir, token).strip():
            raise PullRequestError("Patch produced no changes")
        _git(["-c", f"user.name={GIT_AUTHOR[0]}", "-c", f"user.email={GIT_AUTHOR[1]}",
              "commit", "-m", title], repo_dir, token)
        _git(["push", "origin", f"HEAD:refs/heads/{branch}"], repo_dir, token)  # never forced
    finally:
        if workdir.exists():
            _force_rmtree(workdir)  # never keep customer code around

    client = http or httpx.Client(timeout=30)
    r = client.post(
        f"{s.github_api_base.rstrip('/')}/repos/{repo_full_name}/pulls",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"title": title, "head": branch, "base": default_branch, "body": body},
    )
    if r.status_code >= 400:
        raise PullRequestError(f"GitHub refused the pull request ({r.status_code}): "
                               f"{r.text[:300]}")
    return r.json()["html_url"]


def build_pr_body(*, root_cause: str, evidence: list[str], risk: str, reviewer: str,
                  comment: str, fix_id: str) -> str:
    ev = "\n".join(evidence[:8])
    return (
        f"## Automated fix proposed by DevPilot AI\n\n"
        f"**Root cause:** {root_cause}\n\n"
        f"**Risk:** `{risk}` · **Approved by:** {reviewer}\n"
        + (f"**Reviewer note:** {comment}\n" if comment else "")
        + f"\n<details><summary>Log evidence</summary>\n\n```\n{ev}\n```\n</details>\n\n"
        f"> Opened after human approval (fix `{fix_id}`). DevPilot never pushes to the default "
        f"branch. Please review the diff and let CI run before merging."
    )
