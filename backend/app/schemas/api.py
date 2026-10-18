import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.entities import ApprovalStatus, RiskLevel

_GITHUB_URL = re.compile(
    r"^(?:https?://(?:www\.)?github\.com/|git@github\.com:|github\.com/)"
    r"(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?(?:[/?#].*)?$", re.IGNORECASE)


def normalize_repo(value: str) -> str:
    """Accept `owner/repo` or any GitHub URL form and return `owner/repo`."""
    value = value.strip()
    m = _GITHUB_URL.match(value)
    return f"{m['owner']}/{m['repo']}" if m else value


class RepositoryCreate(BaseModel):
    full_name: str = Field(pattern=r"^[\w.-]+/[\w.-]+$",
                           examples=["octocat/hello-world", "https://github.com/octocat/hello-world"])
    default_branch: str = ""  # empty = look it up on GitHub, falling back to "main"

    @field_validator("full_name", mode="before")
    @classmethod
    def _accept_urls(cls, v):
        return normalize_repo(v) if isinstance(v, str) else v


class RepositoryOut(BaseModel):
    id: str
    full_name: str
    default_branch: str
    created_at: datetime
    diagnosis_count: int = 0
    analysis_status: str | None = None  # queued | running | completed | failed
    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    """A failed GitHub Actions run, plus whether DevPilot has already diagnosed it."""
    id: str
    name: str
    title: str
    branch: str
    sha: str
    url: str
    created_at: str
    conclusion: str
    diagnosis_id: str | None = None
    diagnosing: bool = False  # queued/running: a pipeline run exists but no diagnosis yet
    error: str | None = None  # the last attempt failed (for example a missing token); retry


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
    id: str = ""        # saved to history; empty only if persistence was skipped
    fix_id: str | None = None
    category: str
    root_cause: str
    evidence: list[str]
    confidence: float
    fix_summary: str = ""
    patch: str = ""
    risk: RiskLevel
    model: str
    prompt_version: str = ""
    warnings: list[str] = []


class DecisionIn(BaseModel):
    decision: ApprovalStatus
    reviewer: str = ""  # ignored when sign-in is enabled: the signed-in user is the reviewer
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
    pr_url: str | None = None
    model_config = {"from_attributes": True}


class StoredDiagnosisOut(BaseModel):
    """A persisted diagnosis (webhook, queued GitHub run, or pasted log) with its proposed fix."""
    id: str
    repository: str | None = None       # None for pasted logs
    provider_run_id: str | None = None
    source: str = "run"                 # run | pasted
    created_by: str | None = None
    category: str
    root_cause: str
    evidence: list[str]
    confidence: float
    model: str
    prompt_version: str = ""
    created_at: datetime
    fix: FixOut | None = None


class DeploymentAssistRequest(BaseModel):
    kind: str = Field(default="both", pattern="^(dockerfile|kubernetes|both)$")


class ValidationOut(BaseModel):
    tool: str
    passed: bool
    issues: list[str]


class ArtifactOut(BaseModel):
    filename: str
    kind: str
    source: str  # claude | template | none
    validation: ValidationOut
    content: str | None = None  # withheld unless it passed validation


class DeploymentAssistOut(BaseModel):
    repository: str
    artifacts: list[ArtifactOut]


class DiagnosisDetailOut(StoredDiagnosisOut):
    log_excerpt: str = ""
    warnings: list[str] = []


class CategoryCount(BaseModel):
    category: str
    count: int


class DayCount(BaseModel):
    date: str
    count: int


class StatsOut(BaseModel):
    repositories: int
    diagnoses_total: int
    diagnoses_7d: int
    pending_fixes: int
    approved_fixes: int
    rejected_fixes: int
    prs_opened: int
    approval_rate: float | None = None      # approved / (approved + rejected)
    avg_confidence: float | None = None
    heuristic_share: float | None = None    # share of diagnoses that did not use Claude
    tokens_7d: int = 0
    est_cost_7d_usd: float = 0.0
    by_category: list[CategoryCount]
    per_day: list[DayCount]
