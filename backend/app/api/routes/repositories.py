from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.models.entities import Analysis, PipelineRun, Repository
from app.schemas.api import AnalysisOut, RepositoryCreate, RepositoryOut
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
