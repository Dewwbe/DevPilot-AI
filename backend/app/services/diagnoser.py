"""CI failure diagnosis - the core feature.

Pipeline:  raw log -> redact -> extract failure window -> heuristic hint
           -> Claude (structured) -> validate evidence -> assign risk -> result

Guardrails:
- Evidence lines returned by the model must actually appear in the log
  (rejects hallucinated evidence and lowers confidence).
- Risk is assigned by deterministic rules on the files a patch touches,
  never by the model.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.entities import RiskLevel
from app.services.claude_client import ClaudeClient, LLMUnavailable
from app.services.log_processing import classify_heuristic, extract_failure, redact

CATEGORIES = ["dependency", "test_failure", "lint_type", "docker_build",
              "timeout_infra", "config", "unknown"]

DIAGNOSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORIES},
        "root_cause": {"type": "string", "description": "One or two sentences."},
        "evidence": {"type": "array", "items": {"type": "string"},
                     "description": "Exact log lines copied verbatim that support the cause."},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "fix_summary": {"type": "string"},
        "patch": {"type": "string", "description": "Unified diff, or empty if not applicable."},
        "files_touched": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["category", "root_cause", "evidence", "confidence", "fix_summary",
                 "files_touched"],
}

SYSTEM_PROMPT = """You are a senior build engineer diagnosing a failed CI job.
Rules:
- Base every claim on the supplied log and repository profile. Do not invent files.
- Evidence must be log lines copied exactly.
- If evidence is insufficient, use category "unknown" and confidence below 0.4.
- Propose the smallest safe fix. Never propose disabling tests or security checks."""

HIGH_RISK_PATHS = (".github/workflows/", "Dockerfile", "infra/", "k8s/", "helm/",
                   "terraform/", ".env", "secrets")
LOW_RISK_SUFFIXES = (".md", ".rst")


@dataclass
class DiagnosisResult:
    category: str
    root_cause: str
    evidence: list[str]
    confidence: float
    fix_summary: str
    patch: str
    files_touched: list[str]
    risk: RiskLevel
    model: str = "heuristic"
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    warnings: list[str] = field(default_factory=list)


def assess_risk(files: list[str]) -> RiskLevel:
    if not files:
        return RiskLevel.low
    if any(any(h in f for h in HIGH_RISK_PATHS) for f in files):
        return RiskLevel.high
    if all(f.endswith(LOW_RISK_SUFFIXES) or "/tests/" in f or f.startswith("tests/")
           for f in files):
        return RiskLevel.low
    return RiskLevel.medium


def _validate_evidence(evidence: list[str], log: str) -> tuple[list[str], list[str]]:
    valid = [e for e in evidence if e.strip() and e.strip() in log]
    warnings = []
    if len(valid) < len(evidence):
        warnings.append(f"{len(evidence) - len(valid)} evidence line(s) not found in log; dropped")
    return valid, warnings


def diagnose(raw_log: str, repo_profile: dict, client: ClaudeClient | None = None,
             max_chars: int = 40_000) -> DiagnosisResult:
    log_text = extract_failure(redact(raw_log), max_chars=max_chars)
    hint = classify_heuristic(log_text)

    try:
        client = client or ClaudeClient()
    except LLMUnavailable as exc:
        return DiagnosisResult(
            category=hint.category,
            root_cause="LLM unavailable; heuristic classification only.",
            evidence=hint.evidence, confidence=0.3 if hint.evidence else 0.0,
            fix_summary="", patch="", files_touched=[], risk=RiskLevel.low,
            warnings=[str(exc)],
        )

    user = (f"Repository profile:\n{repo_profile}\n\n"
            f"Heuristic hint: {hint.category}\n\n"
            f"Failure log (redacted, trimmed):\n```\n{log_text}\n```")
    res = client.structured(system=SYSTEM_PROMPT, user=user,
                            tool_name="report_diagnosis", schema=DIAGNOSIS_SCHEMA)
    d = res.data
    evidence, warnings = _validate_evidence(d.get("evidence", []), log_text)
    confidence = float(d.get("confidence", 0))
    if not evidence:
        confidence = min(confidence, 0.3)
        warnings.append("No verifiable evidence; confidence capped at 0.3")

    files = d.get("files_touched", [])
    return DiagnosisResult(
        category=d.get("category", "unknown"), root_cause=d.get("root_cause", ""),
        evidence=evidence, confidence=confidence, fix_summary=d.get("fix_summary", ""),
        patch=d.get("patch", ""), files_touched=files, risk=assess_risk(files),
        model=res.model, input_tokens=res.input_tokens, output_tokens=res.output_tokens,
        latency_ms=res.latency_ms, warnings=warnings,
    )
