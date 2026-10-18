"""Core persistence model.

Repository -> Analysis (repo intelligence snapshot)
Repository -> PipelineRun -> Diagnosis -> ProposedFix -> Approval
Every state change of consequence writes an AuditEvent.
"""
import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class RiskLevel(str, enum.Enum):
    low = "low"          # docs / comments / test-only edits
    medium = "medium"    # source edits, dependency pin changes
    high = "high"        # infra, CI config, deployments, secrets-adjacent files


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class Repository(Base):
    __tablename__ = "repositories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    full_name: Mapped[str] = mapped_column(String(255), unique=True)  # owner/repo
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    analyses: Mapped[list["Analysis"]] = relationship(back_populates="repository")


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    profile: Mapped[dict] = mapped_column(JSON, default=dict)  # languages, frameworks, deps...
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    repository: Mapped[Repository] = relationship(back_populates="analyses")


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))
    provider_run_id: Mapped[str] = mapped_column(String(64))  # GitHub Actions run id
    conclusion: Mapped[str] = mapped_column(String(30))
    head_sha: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Diagnosis(Base):
    __tablename__ = "diagnoses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"))
    category: Mapped[str] = mapped_column(String(50))
    root_cause: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSON, default=list)  # log lines that support it
    confidence: Mapped[float] = mapped_column(Float)
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ProposedFix(Base):
    __tablename__ = "proposed_fixes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    diagnosis_id: Mapped[str] = mapped_column(ForeignKey("diagnoses.id"))
    summary: Mapped[str] = mapped_column(Text)
    patch: Mapped[str] = mapped_column(Text, default="")  # unified diff
    risk: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel))
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.pending
    )
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CheckRun(Base):
    """Result of running static/test checks on a clone of a repository (Phase 2)."""
    __tablename__ = "check_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))
    status: Mapped[str] = mapped_column(String(20), default="queued")  # + running|completed|failed
    results: Mapped[list] = mapped_column(JSON, default=list)  # one entry per check
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor: Mapped[str] = mapped_column(String(255))  # user id or "system"/"ai"
    action: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(String(255))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
