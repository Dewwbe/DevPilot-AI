"""GitHub webhook receiver: a failed workflow run is diagnosed without manual action."""
import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.core.logging import log
from app.models.entities import PipelineRun, Repository
from app.services import audit

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# Conclusions of a finished run worth diagnosing.
FAILED_CONCLUSIONS = {"failure", "timed_out"}


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    """Validate GitHub's X-Hub-Signature-256 (HMAC-SHA256 of the raw body)."""
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


@router.post("/github", status_code=202)
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str | None = Header(default=None),
    session: Session = Depends(get_session),
):
    secret = get_settings().github_webhook_secret
    if not secret:
        raise HTTPException(503, "Webhook disabled: DEVPILOT_GITHUB_WEBHOOK_SECRET is not set")
    body = await request.body()
    if not verify_signature(secret, body, x_hub_signature_256):
        raise HTTPException(401, "Invalid signature")

    if x_github_event == "ping":
        return {"status": "pong"}
    if x_github_event != "workflow_run":
        return {"status": "ignored", "reason": f"event {x_github_event or 'unknown'}"}

    try:
        payload = json.loads(body)
        run = payload["workflow_run"]
        full_name = payload["repository"]["full_name"]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, "Malformed payload") from None

    if payload.get("action") != "completed" or run.get("conclusion") not in FAILED_CONCLUSIONS:
        return {"status": "ignored", "reason": "not a failed completed run"}

    repo = session.query(Repository).filter_by(full_name=full_name).first()
    if not repo:
        return {"status": "ignored", "reason": "repository not connected"}

    run_id = str(run["id"])
    if session.query(PipelineRun).filter_by(repository_id=repo.id,
                                            provider_run_id=run_id).first():
        return {"status": "ignored", "reason": "already processed"}  # GitHub retries deliveries

    pipeline_run = PipelineRun(repository_id=repo.id, provider_run_id=run_id,
                               conclusion=run["conclusion"], head_sha=run.get("head_sha", ""))
    session.add(pipeline_run)
    audit.record(session, actor="github", action="webhook.workflow_run_failed",
                 target=full_name, detail={"run_id": run_id, "name": run.get("name", "")})
    session.commit()

    from app.workers.tasks import diagnose_run_task

    diagnose_run_task.delay(pipeline_run.id)
    log.info("webhook_diagnose_queued", repo=full_name, run_id=run_id)
    return {"status": "queued", "pipeline_run_id": pipeline_run.id}
