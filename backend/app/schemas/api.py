from datetime import datetime

from pydantic import BaseModel, Field

from app.models.entities import ApprovalStatus, RiskLevel


class RepositoryCreate(BaseModel):
    full_name: str = Field(pattern=r"^[\w.-]+/[\w.-]+$", examples=["octocat/hello-world"])
    default_branch: str = "main"


class RepositoryOut(BaseModel):
    id: str
    full_name: str
    default_branch: str
    created_at: datetime
    model_config = {"from_attributes": True}


class AnalysisOut(BaseModel):
    id: str
    status: str
    profile: dict
    created_at: datetime
    model_config = {"from_attributes": True}


class DiagnoseLogRequest(BaseModel):
    """Ad-hoc diagnosis of a pasted log (no GitHub needed) - useful for demos."""
    log: str = Field(min_length=1, max_length=2_000_000)
    repo_profile: dict = {}


class DiagnosisOut(BaseModel):
    category: str
    root_cause: str
    evidence: list[str]
    confidence: float
    fix_summary: str = ""
    patch: str = ""
    risk: RiskLevel
    model: str
    warnings: list[str] = []


class DecisionIn(BaseModel):
    decision: ApprovalStatus
    reviewer: str
    comment: str = ""


class CheckRunOut(BaseModel):
    id: str
    status: str
    results: list
    created_at: datetime
    model_config = {"from_attributes": True}


class FixOut(BaseModel):
    id: str
    summary: str
    patch: str
    risk: RiskLevel
    status: ApprovalStatus
    decided_by: str | None = None
    model_config = {"from_attributes": True}


class StoredDiagnosisOut(BaseModel):
    """A persisted diagnosis (from the webhook or a queued run) with its proposed fix."""
    id: str
    repository: str
    provider_run_id: str
    category: str
    root_cause: str
    evidence: list[str]
    confidence: float
    model: str
    created_at: datetime
    fix: FixOut | None = None
