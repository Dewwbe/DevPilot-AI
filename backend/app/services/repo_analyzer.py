"""Repository intelligence: deterministic detection of languages, frameworks,
dependency manifests, CI config and container files.

Deterministic first, LLM second: Claude only receives this structured profile,
never the full repository.
"""
from __future__ import annotations

import json
import tomllib
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

LANG_BY_EXT = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
    ".jsx": "JavaScript", ".java": "Java", ".go": "Go", ".rs": "Rust", ".cs": "C#",
    ".rb": "Ruby", ".php": "PHP", ".sh": "Shell",
}
IGNORED_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next"}

FRAMEWORK_MARKERS = {
    "fastapi": "FastAPI", "django": "Django", "flask": "Flask", "pytest": "pytest",
    "react": "React", "next": "Next.js", "express": "Express", "@nestjs/core": "NestJS",
    "vite": "Vite", "jest": "Jest", "vitest": "Vitest",
}


@dataclass
class RepoProfile:
    languages: dict[str, int] = field(default_factory=dict)  # language -> file count
    primary_language: str | None = None
    frameworks: list[str] = field(default_factory=list)
    manifests: list[str] = field(default_factory=list)
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    has_dockerfile: bool = False
    has_compose: bool = False
    ci_workflows: list[str] = field(default_factory=list)
    k8s_manifests: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)  # quick risk flags

    def to_dict(self) -> dict:
        return asdict(self)


def _walk(root: Path):
    for p in root.rglob("*"):
        if any(part in IGNORED_DIRS for part in p.relative_to(root).parts):
            continue
        if p.is_file():
            yield p


def _python_deps(root: Path) -> list[str]:
    deps: list[str] = []
    req = root / "requirements.txt"
    if req.exists():
        for line in req.read_text(errors="ignore").splitlines():
            line = line.split("#")[0].strip()
            if line and not line.startswith("-"):
                deps.append(line)
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            data = tomllib.loads(pyproject.read_text())
            deps += data.get("project", {}).get("dependencies", [])
        except tomllib.TOMLDecodeError:
            pass
    return deps


def _node_deps(root: Path) -> list[str]:
    pkg = root / "package.json"
    if not pkg.exists():
        return []
    try:
        data = json.loads(pkg.read_text())
    except json.JSONDecodeError:
        return []
    return sorted({**data.get("dependencies", {}), **data.get("devDependencies", {})})


def analyze_repository(root: str | Path) -> RepoProfile:
    root = Path(root)
    profile = RepoProfile()
    counts: Counter[str] = Counter()

    for f in _walk(root):
        rel = f.relative_to(root).as_posix()
        if lang := LANG_BY_EXT.get(f.suffix):
            counts[lang] += 1
        name = f.name.lower()
        if name == "dockerfile" or name.endswith(".dockerfile"):
            profile.has_dockerfile = True
        if name in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
            profile.has_compose = True
        if rel.startswith(".github/workflows/") and f.suffix in {".yml", ".yaml"}:
            profile.ci_workflows.append(rel)
        if f.suffix in {".yml", ".yaml"}:
            head = f.read_text(errors="ignore")[:2000]
            if "apiVersion:" in head and "kind:" in head:
                profile.k8s_manifests.append(rel)
        if name in {".env", "id_rsa", "credentials.json"}:
            profile.findings.append(f"Possible secret file committed: {rel}")

    profile.languages = dict(counts.most_common())
    profile.primary_language = counts.most_common(1)[0][0] if counts else None

    if py := _python_deps(root):
        profile.manifests.append("python")
        profile.dependencies["python"] = py
    if js := _node_deps(root):
        profile.manifests.append("node")
        profile.dependencies["node"] = js

    all_deps = " ".join(d.lower() for ds in profile.dependencies.values() for d in ds)
    profile.frameworks = sorted({fw for k, fw in FRAMEWORK_MARKERS.items() if k in all_deps})

    for dep in profile.dependencies.get("python", []):
        if not any(op in dep for op in ("==", ">=", "~=", "<")):
            profile.findings.append(f"Unpinned Python dependency: {dep}")
    if not profile.ci_workflows:
        profile.findings.append("No CI workflow found in .github/workflows")

    return profile
