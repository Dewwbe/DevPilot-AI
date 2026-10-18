from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.models.entities import (
    ApprovalStatus,
    AuditEvent,
    Diagnosis,
    PipelineRun,
    ProposedFix,
    Repository,
    RiskLevel,
)
from app.schemas.api import (
    DecisionIn,
    DiagnoseLogRequest,
    DiagnosisOut,
    FixOut,
    StoredDiagnosisOut,
)
from app.services import audit
from app.services.diagnoser import diagnose

router = APIRouter(prefix="/api", tags=["diagnoses"])


@router.post("/diagnose-log", response_model=DiagnosisOut)
def diagnose_log(body: DiagnoseLogRequest):
    """Synchronous diagnosis of a pasted CI log (bounded input, demo-friendly)."""
    r = diagnose(body.log, body.repo_profile, max_chars=get_settings().max_log_chars)
    return DiagnosisOut(category=r.category, root_cause=r.root_cause, evidence=r.evidence,
                        confidence=r.confidence, fix_summary=r.fix_summary, patch=r.patch,
                        risk=r.risk, model=r.model, warnings=r.warnings)


@router.post("/fixes/{fix_id}/decision")
def decide_fix(fix_id: str, body: DecisionIn, session: Session = Depends(get_session)):
    """Human approval gate. High-risk fixes require a written justification."""
    fix = session.get(ProposedFix, fix_id)
    if not fix:
        raise HTTPException(404, "Fix not found")
    if fix.status != ApprovalStatus.pending:
        raise HTTPException(409, f"Fix already {fix.status.value}")
    if (body.decision == ApprovalStatus.approved and fix.risk == RiskLevel.high
            and len(body.comment.strip()) < 10):
        raise HTTPException(422, "High-risk approval requires a justification comment")
    fix.status = body.decision
    fix.decided_by = body.reviewer
    fix.decided_at = datetime.now(UTC)
    audit.record(session, actor=body.reviewer, action=f"fix.{body.decision.value}",
                 target=fix_id, detail={"risk": fix.risk.value, "comment": body.comment})
    session.commit()
    return {"id": fix.id, "status": fix.status.value}


@router.get("/diagnoses", response_model=list[StoredDiagnosisOut])
def list_diagnoses(limit: int = 50, session: Session = Depends(get_session)):
    """Persisted diagnoses (webhook-triggered or queued), newest first, with their fix."""
    rows = (session.query(Diagnosis, PipelineRun, Repository)
            .join(PipelineRun, Diagnosis.pipeline_run_id == PipelineRun.id)
            .join(Repository, PipelineRun.repository_id == Repository.id)
            .order_by(Diagnosis.created_at.desc()).limit(min(limit, 200)).all())
    out = []
    for diag, run, repo in rows:
        fix = session.query(ProposedFix).filter_by(diagnosis_id=diag.id).first()
        out.append(StoredDiagnosisOut(
            id=diag.id, repository=repo.full_name, provider_run_id=run.provider_run_id,
            category=diag.category, root_cause=diag.root_cause, evidence=diag.evidence,
            confidence=diag.confidence, model=diag.model, created_at=diag.created_at,
            fix=FixOut.model_validate(fix) if fix else None))
    return out


@router.get("/audit")
def audit_log(limit: int = 100, session: Session = Depends(get_session)):
    rows = session.query(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit).all()
    return [{"actor": r.actor, "action": r.action, "target": r.target, "detail": r.detail,
             "at": r.created_at.isoformat()} for r in rows]
