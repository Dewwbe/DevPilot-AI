"""Numbers for the dashboard home page."""
from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.metrics import estimate_cost_usd
from app.models.entities import ApprovalStatus, AuditEvent, Diagnosis, ProposedFix, Repository
from app.schemas.api import CategoryCount, DayCount, StatsOut

router = APIRouter(prefix="/api", tags=["stats"])


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # SQLite returns naive datetimes


@router.get("/stats", response_model=StatsOut)
def stats(days: int = 14, session: Session = Depends(get_session)):
    days = min(max(days, 1), 90)
    now = datetime.now(UTC)
    since_chart = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0,
                                                          microsecond=0)
    since_week = now - timedelta(days=7)

    diagnoses = session.query(Diagnosis).all()
    total = len(diagnoses)
    recent = [d for d in diagnoses if _aware(d.created_at) >= since_week]

    status_counts = dict(session.query(ProposedFix.status, func.count())
                         .group_by(ProposedFix.status).all())
    approved = status_counts.get(ApprovalStatus.approved, 0)
    rejected = status_counts.get(ApprovalStatus.rejected, 0)
    decided = approved + rejected

    per_day = Counter(_aware(d.created_at).date().isoformat()
                      for d in diagnoses if _aware(d.created_at) >= since_chart)
    day_rows = [DayCount(date=(since_chart + timedelta(days=i)).date().isoformat(),
                         count=per_day.get((since_chart + timedelta(days=i)).date().isoformat(), 0))
                for i in range(days)]

    by_category = Counter(d.category for d in diagnoses)
    tokens_in = sum(d.input_tokens for d in recent)
    tokens_out = sum(d.output_tokens for d in recent)
    prs = session.query(AuditEvent).filter(AuditEvent.action == "fix.pr_opened").count()

    return StatsOut(
        repositories=session.query(Repository).count(),
        diagnoses_total=total, diagnoses_7d=len(recent),
        pending_fixes=status_counts.get(ApprovalStatus.pending, 0),
        approved_fixes=approved, rejected_fixes=rejected, prs_opened=prs,
        approval_rate=(approved / decided) if decided else None,
        avg_confidence=(sum(d.confidence for d in diagnoses) / total) if total else None,
        heuristic_share=(sum(1 for d in diagnoses if d.model == "heuristic") / total)
        if total else None,
        tokens_7d=tokens_in + tokens_out,
        est_cost_7d_usd=round(estimate_cost_usd(tokens_in, tokens_out), 4),
        by_category=[CategoryCount(category=c, count=n) for c, n in by_category.most_common()],
        per_day=day_rows,
    )
