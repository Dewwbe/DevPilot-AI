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

    # Claude
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5-5"
    claude_max_tokens: int = 2048
    claude_timeout_s: float = 60.0
    claude_max_retries: int = 3

    # Safety
    workspace_root: str = "/tmp/devpilot-workspaces"
    max_log_chars: int = 40_000  # log tail sent to the LLM


@lru_cache
def get_settings() -> Settings:
    return Settings()
