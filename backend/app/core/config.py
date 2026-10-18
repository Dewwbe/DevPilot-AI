"""Application settings loaded from environment variables (12-factor)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DEVPILOT_", extra="ignore")

    env: str = "local"
    database_url: str = "postgresql+psycopg://devpilot:devpilot@postgres:5432/devpilot"
    redis_url: str = "redis://redis:6379/0"

    # GitHub
    github_token: str = ""
    github_webhook_secret: str = ""  # HMAC secret for /api/webhooks/github; empty = disabled

    # Claude
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5-5"
    claude_max_tokens: int = 2048
    claude_timeout_s: float = 60.0
    claude_max_retries: int = 3

    # Safety
    workspace_root: str = "/tmp/devpilot-workspaces"
    max_log_chars: int = 40_000  # log tail sent to the LLM

    # Check runner (throwaway containers for ruff/pytest/eslint/pip-audit on cloned repos)
    runner_image: str = "devpilot-runner:latest"
    runner_workspace_volume: str = "devpilot-workspaces"  # docker volume shared with the worker
    runner_timeout_s: int = 600
    runner_memory: str = "1g"
    runner_cpus: float = 1.0
    runner_network: str = "bridge"  # checks install dependencies; use "none" for offline-only


@lru_cache
def get_settings() -> Settings:
    return Settings()
