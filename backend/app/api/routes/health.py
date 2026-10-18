from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_session

router = APIRouter(tags=["health"])


@router.get("/healthz")
def liveness() -> dict:
    """Kubernetes liveness probe: process is up."""
    return {"status": "ok"}


@router.get("/readyz")
def readiness(session: Session = Depends(get_session)) -> dict:
    """Kubernetes readiness probe: dependencies reachable."""
    session.execute(text("SELECT 1"))
    return {"status": "ready"}
