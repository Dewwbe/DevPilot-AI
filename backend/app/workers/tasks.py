"""Long-running jobs executed by Celery workers, never in the API process."""
from __future__ import annotations

import shutil
from pathlib import Path

from app.core.config import get_settings
from app.core.db import get_session
from app.core.logging import log
from app.models.entities import Analysis, Diagnosis, PipelineRun, ProposedFix, Repository
from app.services import audit
from app.services.diagnoser import diagnose
from app.services.github_client import GitHubClient, shallow_clone
from app.services.repo_analyzer import analyze_repository
from app.workers.celery_app import celery_app


@celery_app.task(name="analyze_repository")
def analyze_repository_task(analysis_id: str) -> None:
    session = next(get_session())
    analysis = session.get(Analysis, analysis_id)
    repo = session.get(Repository, analysis.repository_id)
    workdir = Path(get_settings().workspace_root) / analysis_id
    try:
        analysis.status = "running"
        session.commit()
        shallow_clone(repo.full_name, workdir, repo.default_branch)
        analysis.profile = analyze_repository(workdir).to_dict()
        analysis.status = "completed"
    except Exception as exc:  # noqa: BLE001
        log.exception("analysis_failed", analysis_id=analysis_id)
        analysis.status = "failed"
        analysis.profile = {"error": str(exc)}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)  # never keep customer code around
        audit.record(session, actor="system", action="analysis." + analysis.status,
                     target=repo.full_name)
        session.commit()


@celery_app.task(name="diagnose_run")
def diagnose_run_task(pipeline_run_id: str) -> None:
    session = next(get_session())
    run = session.get(PipelineRun, pipeline_run_id)
    repo = session.get(Repository, run.repository_id)
    gh = GitHubClient()

    logs = "\n".join(gh.job_log(repo.full_name, j["id"])
                     for j in gh.failed_jobs(repo.full_name, int(run.provider_run_id)))
    latest = (session.query(Analysis).filter_by(repository_id=repo.id, status="completed")
              .order_by(Analysis.created_at.desc()).first())
    result = diagnose(logs, latest.profile if latest else {},
                      max_chars=get_settings().max_log_chars)

    diag = Diagnosis(pipeline_run_id=run.id, category=result.category,
                     root_cause=result.root_cause, evidence=result.evidence,
                     confidence=result.confidence, model=result.model,
                     input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                     latency_ms=result.latency_ms)
    session.add(diag)
    session.flush()
    if result.fix_summary:
        session.add(ProposedFix(diagnosis_id=diag.id, summary=result.fix_summary,
                                patch=result.patch, risk=result.risk))
    audit.record(session, actor="ai", action="diagnosis.created", target=run.id,
                 detail={"category": result.category, "confidence": result.confidence,
                         "warnings": result.warnings})
    session.commit()
