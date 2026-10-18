"""CI log pre-processing before anything reaches the LLM.

1. redact()            - strip secrets/tokens (responsible AI use, data minimisation)
2. extract_failure()   - keep only the region around the first errors to bound cost
3. classify_heuristic()- cheap rule-based category, used as a hint and as an
                          offline fallback when the LLM is unavailable
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SECRET_PATTERNS = [
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"), "[REDACTED_ANTHROPIC_KEY]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S+"),
     r"\1=[REDACTED]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"),
     "[REDACTED_PRIVATE_KEY]"),
]

ERROR_MARKERS = re.compile(
    r"(error|failed|failure|exception|traceback|fatal|exit code [1-9]|assert)", re.I
)


def redact(text: str) -> str:
    for pattern, repl in SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def extract_failure(log: str, context: int = 25, max_chars: int = 40_000) -> str:
    """Return windows of lines around error markers, deduplicated, bounded."""
    lines = log.splitlines()
    keep: set[int] = set()
    for i, line in enumerate(lines):
        if ERROR_MARKERS.search(line):
            keep.update(range(max(0, i - context), min(len(lines), i + context + 1)))
    if not keep:  # no markers: fall back to the tail
        return "\n".join(lines[-200:])[-max_chars:]
    out, prev = [], -2
    for i in sorted(keep):
        if i != prev + 1:
            out.append("...")
        out.append(lines[i])
        prev = i
    return "\n".join(out)[-max_chars:]


@dataclass
class HeuristicResult:
    category: str
    evidence: list[str]


RULES: list[tuple[str, re.Pattern]] = [
    ("dependency", re.compile(r"(ModuleNotFoundError|No matching distribution|npm ERR! 404|"
                              r"Cannot find module|ERESOLVE|ResolutionImpossible)")),
    ("test_failure", re.compile(r"(FAILED .*::|AssertionError|\d+ failed|Tests:\s+\d+ failed)")),
    ("lint_type", re.compile(r"(ruff|flake8|eslint|mypy|error TS\d+)", re.I)),
    ("docker_build", re.compile(r"(failed to solve|COPY failed|docker build|executor failed)")),
    ("timeout_infra", re.compile(r"(timed out|ETIMEDOUT|rate limit|503 Service|No space left)")),
    ("config", re.compile(r"(Invalid workflow file|yaml: line \d+|unknown key|"
                          r"KeyError: '\w+_ENV)")),
]


def classify_heuristic(log: str) -> HeuristicResult:
    for category, rx in RULES:
        hits = [ln.strip() for ln in log.splitlines() if rx.search(ln)]
        if hits:
            return HeuristicResult(category, hits[:5])
    return HeuristicResult("unknown", [])
