"""Deployment assistant: generate a Dockerfile / Kubernetes manifest for a profiled repository.

Nothing is shown to the user unless it passed validation (hadolint for Dockerfiles, kubeconform
for manifests). If a validator is missing or fails, the content is withheld and only the issues
are returned. Claude gets one repair attempt with the validator's findings; if that still fails
(or Claude is unavailable) a deterministic, pre-validated template is used instead.
"""
from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core import metrics
from app.core.logging import log
from app.services.claude_client import ClaudeClient

Runner = Callable[[list[str], str], tuple[int, str]]  # (argv, stdin) -> (exit code, stdout)

SYSTEM_PROMPT = """You are a platform engineer writing production container and Kubernetes files.
Requirements for everything you produce:
- Dockerfile: pinned base image tag (never :latest), multi-stage when a build step exists, runs
  as a non-root USER, no secrets, --no-cache-dir/--no-install-recommends style flags, EXPOSE.
- Kubernetes: a Deployment and a Service in one YAML stream; readiness and liveness probes,
  resource requests and limits, runAsNonRoot, allowPrivilegeEscalation false,
  readOnlyRootFilesystem.
- Base everything on the supplied repository profile only. Do not invent files or commands.
Return only through the tool."""

SCHEMA = {
    "type": "object",
    "properties": {
        "dockerfile": {"type": "string", "description": "Complete Dockerfile, or empty."},
        "k8s_manifest": {"type": "string", "description": "Multi-document YAML, or empty."},
        "notes": {"type": "string"},
    },
    "required": ["dockerfile", "k8s_manifest", "notes"],
}


@dataclass
class Validation:
    tool: str
    passed: bool
    issues: list[str] = field(default_factory=list)


@dataclass
class Artifact:
    filename: str
    kind: str                  # "dockerfile" | "kubernetes"
    source: str                # "claude" | "template" | "none"
    validation: Validation
    content: str | None = None  # only set when validation passed


def _run(argv: list[str], stdin: str) -> tuple[int, str]:
    proc = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=60)
    return proc.returncode, proc.stdout or proc.stderr


def validate_dockerfile(text: str, runner: Runner = _run) -> Validation:
    try:
        code, out = runner(["hadolint", "--format", "json", "--failure-threshold", "warning", "-"],
                           text)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return Validation("hadolint", False, [f"hadolint unavailable: {exc}"])
    issues: list[str] = []
    try:
        for f in json.loads(out or "[]"):
            if f.get("level") in ("error", "warning"):
                issues.append(f"line {f.get('line')}: {f.get('code')} {f.get('message')}")
    except json.JSONDecodeError:
        issues.append(f"unparseable hadolint output: {out[:200]}")
    return Validation("hadolint", code == 0 and not issues, issues)


def validate_manifest(text: str, runner: Runner = _run) -> Validation:
    try:
        code, out = runner(["kubeconform", "-strict", "-summary", "-output", "json", "-"], text)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return Validation("kubeconform", False, [f"kubeconform unavailable: {exc}"])
    issues: list[str] = []
    try:
        data = json.loads(out or "{}")
        for r in data.get("resources", []):
            if r.get("status") not in ("statusValid", "statusSkipped"):
                issues.append(f"{r.get('kind')}/{r.get('name')}: {r.get('msg') or r.get('status')}")
        if not data.get("resources") and not data.get("summary", {}).get("valid"):
            issues.append("no Kubernetes resources found")
    except json.JSONDecodeError:
        issues.append(f"unparseable kubeconform output: {out[:200]}")
    return Validation("kubeconform", code == 0 and not issues, issues)


# ---------------- deterministic templates (offline fallback) ----------------

def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", name.lower().split("/")[-1]).strip("-") or "app"


def template_dockerfile(profile: dict) -> str | None:
    lang = profile.get("primary_language")
    deps = profile.get("manifests", [])
    if lang == "Python":
        install = ("COPY requirements.txt ./\nRUN pip install --no-cache-dir -r requirements.txt"
                   if "requirements.txt" in deps else
                   "COPY pyproject.toml ./\nCOPY . .\nRUN pip install --no-cache-dir .")
        return (
            "FROM python:3.12-slim\n"
            "WORKDIR /app\n"
            "RUN useradd --create-home --uid 10001 app\n"
            f"{install}\n"
            "COPY . .\n"
            "USER app\n"
            "EXPOSE 8000\n"
            'CMD ["python", "-m", "http.server", "8000"]\n'
        )
    if lang in ("JavaScript", "TypeScript"):
        return (
            "FROM node:20-alpine AS build\n"
            "WORKDIR /src\n"
            "COPY package*.json ./\n"
            "RUN npm ci\n"
            "COPY . .\n"
            "RUN npm run build --if-present\n\n"
            "FROM node:20-alpine\n"
            "WORKDIR /app\n"
            "COPY --from=build /src /app\n"
            "USER node\n"
            "EXPOSE 3000\n"
            'CMD ["npm", "start"]\n'
        )
    return None


def template_manifest(profile: dict, repo_name: str) -> str | None:
    lang = profile.get("primary_language")
    port = {"Python": 8000, "JavaScript": 3000, "TypeScript": 3000}.get(lang or "")
    if not port:
        return None
    name = _slug(repo_name)
    return f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  labels: {{ app: {name} }}
spec:
  replicas: 2
  selector:
    matchLabels: {{ app: {name} }}
  template:
    metadata:
      labels: {{ app: {name} }}
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
      containers:
        - name: {name}
          image: {name}:latest
          ports:
            - containerPort: {port}
          readinessProbe:
            tcpSocket: {{ port: {port} }}
          livenessProbe:
            tcpSocket: {{ port: {port} }}
            initialDelaySeconds: 10
          resources:
            requests: {{ cpu: 100m, memory: 128Mi }}
            limits: {{ cpu: 500m, memory: 256Mi }}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
---
apiVersion: v1
kind: Service
metadata:
  name: {name}
spec:
  selector: {{ app: {name} }}
  ports:
    - port: 80
      targetPort: {port}
"""


# ---------------- orchestration ----------------

def _validated(kind: str, filename: str, content: str | None, source: str,
               validate: Callable[[str], Validation]) -> Artifact:
    if not content or not content.strip():
        return Artifact(filename, kind, "none",
                        Validation("-", False, ["nothing was generated for this profile"]))
    v = validate(content)
    return Artifact(filename, kind, source, v, content if v.passed else None)


def _ask_claude(client: Any, profile: dict, repo_name: str, want: set[str],
                feedback: list[str]) -> dict[str, str] | None:
    user = f"Repository: {repo_name}\nProfile:\n{json.dumps(profile, indent=2)[:6000]}\n"
    user += f"Generate: {', '.join(sorted(want))}.\n"
    if feedback:
        user += "Your previous attempt failed validation. Fix these findings:\n- " + \
                "\n- ".join(feedback[:15]) + "\n"
    try:
        res = client.structured(system=SYSTEM_PROMPT, user=user,
                                tool_name="propose_deployment_files", schema=SCHEMA)
    except Exception as exc:  # noqa: BLE001  (outage, open circuit breaker, missing key)
        log.warning("deployment_assist_llm_failed", error=str(exc)[:200])
        return None
    metrics.record_llm_usage(res.model, res.input_tokens, res.output_tokens)
    return res.data


def generate(profile: dict, repo_name: str, kind: str = "both",
             client: Any | None = None, use_llm: bool = True,
             runner: Runner = _run) -> list[Artifact]:
    """kind: "dockerfile" | "kubernetes" | "both". Returns only validated content."""
    want = {"dockerfile", "kubernetes"} if kind == "both" else {kind}
    if use_llm and client is None:
        try:
            client = ClaudeClient()
        except Exception:  # noqa: BLE001  (no API key)
            client = None

    specs = {
        "dockerfile": ("Dockerfile", "dockerfile", lambda t: validate_dockerfile(t, runner),
                       template_dockerfile(profile)),
        "kubernetes": ("k8s.yaml", "k8s_manifest", lambda t: validate_manifest(t, runner),
                       template_manifest(profile, repo_name)),
    }
    out: dict[str, Artifact] = {}

    if client is not None and use_llm:
        feedback: list[str] = []
        for _attempt in range(2):  # initial try + one repair using validator findings
            data = _ask_claude(client, profile, repo_name, want - out.keys(), feedback)
            if data is None:
                break
            feedback = []
            for k in sorted(want - out.keys()):
                filename, field_name, validate, _tpl = specs[k]
                art = _validated(k, filename, data.get(field_name), "claude", validate)
                if art.validation.passed:
                    out[k] = art
                else:
                    feedback += [f"{filename}: {i}" for i in art.validation.issues]
            if out.keys() >= want:
                break

    for k in sorted(want - out.keys()):  # deterministic fallback for anything still missing
        filename, _f, validate, tpl = specs[k]
        out[k] = _validated(k, filename, tpl, "template", validate)
    return [out[k] for k in sorted(out)]
