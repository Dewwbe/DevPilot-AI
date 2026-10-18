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
    DiagnosisDetailOut,
    DiagnosisOut,
    FixOut,
    StoredDiagnosisOut,
)
from app.services import audit
from app.services.auth import User, require_user
from app.services.diagnoser import diagnose
from app.services.log_processing import extract_failure, redact

router = APIRouter(prefix="/api", tags=["diagnoses"])

EXCERPT_CHARS = 4000


@router.post("/diagnose-log", response_model=DiagnosisOut)
def diagnose_log(body: DiagnoseLogRequest, session: Session = Depends(get_session),
                 user: User = Depends(require_user)):
    """Diagnose a pasted CI log and save it to history (so it can be reviewed and approved)."""
    r = diagnose(body.log, body.repo_profile, max_chars=get_settings().max_log_chars)
    metrics.record_diagnosis(r.category, r.model, r.input_tokens, r.output_tokens, r.latency_ms)

    diag = Diagnosis(
        pipeline_run_id=None, source="pasted", created_by=user.login,
        log_excerpt=extract_failure(redact(body.log), max_chars=EXCERPT_CHARS),
        category=r.category, root_cause=r.root_cause, evidence=r.evidence,
        confidence=r.confidence, model=r.model, input_tokens=r.input_tokens,
        output_tokens=r.output_tokens, latency_ms=r.latency_ms, prompt_version=r.prompt_version)
    session.add(diag)
    session.flush()
    fix_id = None
    if r.fix_summary:
        fix = ProposedFix(diagnosis_id=diag.id, summary=r.fix_summary, patch=r.patch, risk=r.risk)
        session.add(fix)
        session.flush()
        fix_id = fix.id
    audit.record(session, actor=user.login, action="diagnosis.pasted", target=diag.id,
                 detail={"category": r.category, "model": r.model})
    session.commit()
    return DiagnosisOut(
        id=diag.id, fix_id=fix_id, category=r.category, root_cause=r.root_cause,
        evidence=r.evidence, confidence=r.confidence, fix_summary=r.fix_summary, patch=r.patch,
        risk=r.risk, model=r.model, prompt_version=r.prompt_version, warnings=r.warnings)


@router.post("/fixes/{fix_id}/decision")
def decide_fix(fix_id: str, body: DecisionIn, session: Session = Depends(get_session),
               user: User = Depends(require_user)):
    """Human approval gate. High-risk fixes require a written justification."""
    fix = session.get(ProposedFix, fix_id)
    if not fix:
        raise HTTPException(404, "Fix not found")
    if fix.status != ApprovalStatus.pending:
        raise HTTPException(409, f"Fix already {fix.status.value}")
    if (body.decision == ApprovalStatus.approved and fix.risk == RiskLevel.high
            and len(body.comment.strip()) < 10):
        raise HTTPException(422, "High-risk approval requires a justification comment")
    # With sign-in on, the reviewer is the authenticated user, never a client-supplied name.
    reviewer = user.login if user.authenticated else (body.reviewer.strip() or "anonymous")
    fix.status = body.decision
    fix.decided_by = reviewer
    fix.decided_at = datetime.now(UTC)
    audit.record(session, actor=reviewer, action=f"fix.{body.decision.value}",
                 target=fix_id, detail={"risk": fix.risk.value, "comment": body.comment})
    session.commit()
    metrics.FIX_DECISIONS.labels(decision=body.decision.value).inc()
    return {"id": fix.id, "status": fix.status.value, "decided_by": reviewer}


@router.post("/fixes/{fix_id}/open-pr", status_code=202)
def open_pr(fix_id: str, session: Session = Depends(get_session),
            user: User = Depends(require_user)):
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
    diag = session.get(Diagnosis, fix.diagnosis_id)
    if diag is None or diag.pipeline_run_id is None:
        raise HTTPException(422, "Fixes for pasted logs have no repository, so no PR can be opened")
    if fix.pr_url:
        raise HTTPException(409, f"Pull request already opened: {fix.pr_url}")
    if not app_configured():
        raise HTTPException(503, "GitHub App is not configured (DEVPILOT_GITHUB_APP_*)")
    audit.record(session, actor=fix.decided_by or user.login, action="fix.pr_requested",
                 target=fix.id)
    session.commit()
    open_fix_pr_task.delay(fix.id)
    return {"id": fix.id, "status": "queued"}


def _stored(diag: Diagnosis, run: PipelineRun | None, repo: Repository | None,
            fix: ProposedFix | None, cls=StoredDiagnosisOut, **extra):
    return cls(
        id=diag.id, repository=repo.full_name if repo else None,
        provider_run_id=run.provider_run_id if run else None, source=diag.source,
        created_by=diag.created_by, category=diag.category, root_cause=diag.root_cause,
        evidence=diag.evidence, confidence=diag.confidence, model=diag.model,
        prompt_version=diag.prompt_version, created_at=diag.created_at,
        fix=FixOut.model_validate(fix) if fix else None, **extra)


def _base_query(session: Session):
    return (session.query(Diagnosis, PipelineRun, Repository, ProposedFix)
            .outerjoin(PipelineRun, Diagnosis.pipeline_run_id == PipelineRun.id)
            .outerjoin(Repository, PipelineRun.repository_id == Repository.id)
            .outerjoin(ProposedFix, ProposedFix.diagnosis_id == Diagnosis.id))


@router.get("/diagnoses", response_model=list[StoredDiagnosisOut])
def list_diagnoses(limit: int = 50, offset: int = 0, repository: str | None = None,
                   category: str | None = None, source: str | None = None,
                   status: str | None = None, session: Session = Depends(get_session)):
    """Diagnosis history, newest first. Filters: repository (owner/repo), category, source
    (run|pasted) and status (the fix's pending|approved|rejected)."""
    q = _base_query(session)
    if repository:
        q = q.filter(Repository.full_name == repository)
    if category:
        q = q.filter(Diagnosis.category == category)
    if source:
        q = q.filter(Diagnosis.source == source)
    if status:
        try:
            q = q.filter(ProposedFix.status == ApprovalStatus(status))
        except ValueError:
            raise HTTPException(422, "status must be pending, approved or rejected") from None
    rows = (q.order_by(Diagnosis.created_at.desc()).offset(max(offset, 0))
            .limit(min(max(limit, 1), 200)).all())
    return [_stored(*row) for row in rows]


@router.get("/diagnoses/{diagnosis_id}", response_model=DiagnosisDetailOut)
def get_diagnosis(diagnosis_id: str, session: Session = Depends(get_session)):
    row = _base_query(session).filter(Diagnosis.id == diagnosis_id).first()
    if not row:
        raise HTTPException(404, "Diagnosis not found")
    return _stored(*row, cls=DiagnosisDetailOut, log_excerpt=row[0].log_excerpt)


@router.get("/audit")
def audit_log(limit: int = 100, session: Session = Depends(get_session)):
    rows = session.query(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit).all()
    return [{"actor": r.actor, "action": r.action, "target": r.target, "detail": r.detail,
             "at": r.created_at.isoformat()} for r in rows]
