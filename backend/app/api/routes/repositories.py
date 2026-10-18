from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.models.entities import Analysis, CheckRun, PipelineRun, Repository
from app.schemas.api import (
    AnalysisOut,
    ArtifactOut,
    CheckRunOut,
    DeploymentAssistOut,
    DeploymentAssistRequest,
    RepositoryCreate,
    RepositoryOut,
    ValidationOut,
)
from app.services import audit

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


@router.post("", response_model=RepositoryOut, status_code=201)
def connect_repository(body: RepositoryCreate, session: Session = Depends(get_session)):
    if session.query(Repository).filter_by(full_name=body.full_name).first():
        raise HTTPException(409, "Repository already connected")
    repo = Repository(full_name=body.full_name, default_branch=body.default_branch)
    session.add(repo)
    audit.record(session, actor="user", action="repository.connected", target=body.full_name)
    session.commit()
    return repo


@router.get("", response_model=list[RepositoryOut])
def list_repositories(session: Session = Depends(get_session)):
    return session.query(Repository).order_by(Repository.created_at.desc()).all()


@router.post("/{repo_id}/analyses", response_model=AnalysisOut, status_code=202)
def start_analysis(repo_id: str, session: Session = Depends(get_session)):
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


@router.post("/{repo_id}/runs/{provider_run_id}/diagnose", status_code=202)
def diagnose_run(repo_id: str, provider_run_id: str, session: Session = Depends(get_session)):
    from app.workers.tasks import diagnose_run_task

    if not session.get(Repository, repo_id):
        raise HTTPException(404, "Repository not found")
    run = PipelineRun(repository_id=repo_id, provider_run_id=provider_run_id,
                      conclusion="failure")
    session.add(run)
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
