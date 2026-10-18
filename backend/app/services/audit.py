"""Append-only audit trail helper."""
from sqlalchemy.orm import Session

from app.models.entities import AuditEvent


def record(session: Session, *, actor: str, action: str, target: str,
           detail: dict | None = None) -> None:
    session.add(AuditEvent(actor=actor, action=action, target=target, detail=detail or {}))
