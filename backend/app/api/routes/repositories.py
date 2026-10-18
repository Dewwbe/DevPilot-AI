from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.models.entities import Analysis, AuditEvent, CheckRun, Diagnosis, PipelineRun, Repository
from app.schemas.api import (
    AnalysisOut,
    ArtifactOut,
    CheckRunOut,
    DeploymentAssistOut,
    DeploymentAssistRequest,
    RepositoryCreate,
    RepositoryOut,
    RunOut,
    ValidationOut,
)
from app.services import audit
from app.services.auth import User, require_user
from app.services.github_client import GitHubError, lookup_repo, recent_failed_runs

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


@router.post("", response_model=RepositoryOut, status_code=201)
def connect_repository(body: RepositoryCreate, session: Session = Depends(get_session),
                       user: User = Depends(require_user)):
    """Connect a repository by `owner/repo` or any github.com URL. GitHub is asked for the real
    name and default branch; a repository that does not exist is rejected with the reason."""
    try:
        meta = lookup_repo(body.full_name)
    except GitHubError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    full_name = (meta or {}).get("full_name") or body.full_name  # canonical capitalisation
    if session.query(Repository).filter(func.lower(Repository.full_name) == full_name.lower()
                                         ).first():
        raise HTTPException(409, "Repository already connected")
    branch = body.default_branch or (meta or {}).get("default_branch") or "main"
    repo = Repository(full_name=full_name, default_branch=branch)
    session.add(repo)
    audit.record(session, actor=user.login, action="repository.connected", target=full_name)
    session.commit()
    return repo


@router.get("", response_model=list[RepositoryOut])
def list_repositories(session: Session = Depends(get_session)):
    repos = session.query(Repository).order_by(Repository.created_at.desc()).all()
    counts = dict(session.query(PipelineRun.repository_id, func.count(Diagnosis.id))
                  .join(Diagnosis, Diagnosis.pipeline_run_id == PipelineRun.id)
                  .group_by(PipelineRun.repository_id).all())
    latest: dict[str, str] = {}
    for a in session.query(Analysis).order_by(Analysis.created_at.desc()).all():
        latest.setdefault(a.repository_id, a.status)  # newest first, so first one wins
    out = []
    for r in repos:
        item = RepositoryOut.model_validate(r)
        item.diagnosis_count = counts.get(r.id, 0)
        item.analysis_status = latest.get(r.id)
        out.append(item)
    return out


@router.post("/{repo_id}/analyses", response_model=AnalysisOut, status_code=202)
def start_analysis(repo_id: str, session: Session = Depends(get_session),
                   _user: User = Depends(require_user)):
    from app.workers.tasks import analyze_repository_task

    if not session.get(Repository, repo_id):
        raise HTTPException(404, "Repository not found")
    analysis = Analysis(repository_id=repo_id)
    session.add(analysis)
    session.commit()
    analyze_repository_task.delay(analysis.id)
    return analysis


@router.get("/{repo_id}/analyses", response_model=list[AnalysisOut])
def list_analyses(repo_id: str, session: Session = Depends(get_session)):
    return (session.query(Analysis).filter_by(repository_id=repo_id)
            .order_by(Analysis.created_at.desc()).all())


@router.get("/{repo_id}/runs", response_model=list[RunOut])
def list_runs(repo_id: str, limit: int = 15, session: Session = Depends(get_session)):
    """Recent failed GitHub Actions runs, marked with whether they have been diagnosed."""
    repo = session.get(Repository, repo_id)
    if not repo:
        raise HTTPException(404, "Repository not found")
    try:
        runs = recent_failed_runs(repo.full_name, min(max(limit, 1), 30))
    except GitHubError as exc:
        raise HTTPException(exc.status, str(exc)) from exc

    known = {pr.provider_run_id: pr for pr in
             session.query(PipelineRun).filter_by(repository_id=repo_id).all()}
    diagnosis_by_run = {d.pipeline_run_id: d.id for d in session.query(Diagnosis).filter(
        Diagnosis.pipeline_run_id.in_([pr.id for pr in known.values()] or [""])).all()}
    failures = {e.target: (e.detail or {}).get("error", "Diagnosis failed") for e in
                session.query(AuditEvent).filter(AuditEvent.action == "diagnosis.failed").all()}

    out = []
    for r in runs:
        pr = known.get(r["id"])
        diag_id = diagnosis_by_run.get(pr.id) if pr else None
        error = failures.get(pr.id) if pr and not diag_id else None
        out.append(RunOut(**r, diagnosis_id=diag_id, error=error,
                          diagnosing=bool(pr and not diag_id and not error)))
    return out


@router.post("/{repo_id}/runs/{provider_run_id}/diagnose", status_code=202)
def diagnose_run(repo_id: str, provider_run_id: str, session: Session = Depends(get_session),
                 user: User = Depends(require_user)):
    """Queue a diagnosis of one failed run. Safe to click twice: an existing run is reused, and a
    run whose earlier attempt failed is retried."""
    from app.workers.tasks import diagnose_run_task

    if not session.get(Repository, repo_id):
        raise HTTPException(404, "Repository not found")
    run = session.query(PipelineRun).filter_by(repository_id=repo_id,
                                               provider_run_id=provider_run_id).first()
    if run:
        diag = session.query(Diagnosis).filter_by(pipeline_run_id=run.id).first()
        if diag:
            return {"pipeline_run_id": run.id, "status": "done", "diagnosis_id": diag.id}
    else:
        run = PipelineRun(repository_id=repo_id, provider_run_id=provider_run_id,
                          conclusion="failure")
        session.add(run)
        session.flush()  # assigns run.id
    audit.record(session, actor=user.login, action="run.diagnose_requested", target=run.id,
                 detail={"provider_run_id": provider_run_id})
    session.commit()
    diagnose_run_task.delay(run.id)
    return {"pipeline_run_id": run.id, "status": "queued"}


@router.post("/{repo_id}/checks", response_model=CheckRunOut, status_code=202)
def start_checks(repo_id: str, session: Session = Depends(get_session)):
    """Queue ruff/pytest/eslint/pip-audit in throwaway containers on a fresh clone."""
    from app.workers.tasks import run_checks_task

    if not session.get(Repository, repo_id):
        raise HTTPException(404, "Repository not found")
    check = CheckRun(repository_id=repo_id)
    session.add(check)
    session.commit()
    run_checks_task.delay(check.id)
    return check


@router.get("/{repo_id}/checks", response_model=list[CheckRunOut])
def list_checks(repo_id: str, session: Session = Depends(get_session)):
    return (session.query(CheckRun).filter_by(repository_id=repo_id)
            .order_by(CheckRun.created_at.desc()).limit(20).all())


@router.post("/{repo_id}/deployment-assist", response_model=DeploymentAssistOut)
def deployment_assist(repo_id: str, body: DeploymentAssistRequest,
                      session: Session = Depends(get_session)):
    """Generate a Dockerfile / Kubernetes manifest from the repo profile.

    Content is returned only if it passed hadolint / kubeconform validation.
    """
    from app.services.deployment_assistant import generate

    repo = session.get(Repository, repo_id)
    if not repo:
        raise HTTPException(404, "Repository not found")
    analysis = (session.query(Analysis).filter_by(repository_id=repo_id, status="completed")
                .order_by(Analysis.created_at.desc()).first())
    if not analysis:
        raise HTTPException(409, "Run a repository analysis first")

    artifacts = generate(analysis.profile, repo.full_name, kind=body.kind)
    audit.record(session, actor="ai", action="deployment.generated", target=repo.full_name,
                 detail={"kind": body.kind, "results": {
                     a.filename: {"source": a.source, "passed": a.validation.passed}
                     for a in artifacts}})
    session.commit()
    return DeploymentAssistOut(repository=repo.full_name, artifacts=[
        ArtifactOut(filename=a.filename, kind=a.kind, source=a.source, content=a.content,
                    validation=ValidationOut(tool=a.validation.tool, passed=a.validation.passed,
                                             issues=a.validation.issues))
        for a in artifacts])
