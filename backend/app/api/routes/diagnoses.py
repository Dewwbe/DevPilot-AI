from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core import metrics
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
    metrics.record_diagnosis(r.category, r.model, r.input_tokens, r.output_tokens, r.latency_ms)
    return DiagnosisOut(category=r.category, root_cause=r.root_cause, evidence=r.evidence,
                        confidence=r.confidence, fix_summary=r.fix_summary, patch=r.patch,
                        risk=r.risk, model=r.model, prompt_version=r.prompt_version,
                        warnings=r.warnings)


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
    metrics.FIX_DECISIONS.labels(decision=body.decision.value).inc()
    return {"id": fix.id, "status": fix.status.value}


@router.post("/fixes/{fix_id}/open-pr", status_code=202)
def open_pr(fix_id: str, session: Session = Depends(get_session)):
    """Open a pull request (new branch, never the default branch) for an approved fix."""
    from app.services.github_app import app_configured
    from app.workers.tasks import open_fix_pr_task

    fix = session.get(ProposedFix, fix_id)
    if not fix:
        raise HTTPException(404, "Fix not found")
    if fix.status != ApprovalStatus.approved:
        raise HTTPException(409, "Only approved fixes can be opened as a pull request")
    if not fix.patch.strip():
        raise HTTPException(422, "This fix has no patch")
    if fix.pr_url:
        raise HTTPException(409, f"Pull request already opened: {fix.pr_url}")
    if not app_configured():
        raise HTTPException(503, "GitHub App is not configured (DEVPILOT_GITHUB_APP_*)")
    audit.record(session, actor=fix.decided_by or "system", action="fix.pr_requested",
                 target=fix.id)
    session.commit()
    open_fix_pr_task.delay(fix.id)
    return {"id": fix.id, "status": "queued"}


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
            confidence=diag.confidence, model=diag.model,
            prompt_version=diag.prompt_version, created_at=diag.created_at,
            fix=FixOut.model_validate(fix) if fix else None))
    return out


@router.get("/audit")
def audit_log(limit: int = 100, session: Session = Depends(get_session)):
    rows = session.query(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit).all()
    return [{"actor": r.actor, "action": r.action, "target": r.target, "detail": r.detail,
             "at": r.created_at.isoformat()} for r in rows]
