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
