"""Per-repository daily LLM token budget (cost control and abuse protection)."""
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import Diagnosis, PipelineRun


def tokens_used_today(session: Session, repo_id: str) -> int:
    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    total = (session.query(func.coalesce(
                func.sum(Diagnosis.input_tokens + Diagnosis.output_tokens), 0))
             .join(PipelineRun, Diagnosis.pipeline_run_id == PipelineRun.id)
             .filter(PipelineRun.repository_id == repo_id, Diagnosis.created_at >= day_start)
             .scalar())
    return int(total or 0)


def budget_exhausted(session: Session, repo_id: str) -> bool:
    budget = get_settings().repo_daily_token_budget
    return budget > 0 and tokens_used_today(session, repo_id) >= budget
