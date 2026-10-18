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

    # AI reliability (Phase 3)
    repo_daily_token_budget: int = 200_000  # per repository per UTC day; 0 = unlimited
    llm_breaker_threshold: int = 5          # consecutive Claude failures before the breaker opens
    llm_breaker_cooldown_s: int = 60        # how long it stays open before a trial request
    # Cost estimate for dashboards (USD per million tokens). Set to your model's actual pricing.
    price_input_per_mtok: float = 3.0
    price_output_per_mtok: float = 15.0

    # GitHub App used to open pull requests for approved fixes (contents:write +
    # pull_requests:write only). Leave empty to disable PR creation.
    github_app_id: str = ""
    github_app_private_key: str = ""  # PEM; "\n" escapes are accepted for env files
    github_app_installation_id: str = ""
    github_git_base: str = "https://github.com"
    github_api_base: str = "https://api.github.com"

    # Sign in with GitHub (OAuth 2.0 authorization-code flow). The three secrets below must all be
    # set to turn authentication on; otherwise the API is open (local development).
    github_oauth_client_id: str = ""
    github_oauth_client_secret: str = ""
    # Signs session cookies; use a long random value (openssl rand -hex 32).
    session_secret: str = ""
    # Comma-separated GitHub logins allowed to sign in; empty = any GitHub account.
    allowed_github_users: str = ""
    # Public origin, e.g. https://devpilot.example.com; empty = derived from the request headers.
    public_base_url: str = ""
    session_ttl_hours: int = 12
    github_oauth_base: str = "https://github.com"

    # Operations
    # Run Alembic on API start. The Helm chart sets this to false and runs a migration Job.
    auto_migrate: bool = True
    metrics_port: int = 9100   # Prometheus endpoint exposed by Celery workers

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
