# DevPilot AI — Implementation Roadmap

Planning assumption: ~15–20 hours per week, one developer. Each phase ends with a demo-able
increment and a tagged release (`v0.1`, `v0.2`, `v1.0`). Durations are estimates; adjust after
Sprint 1 velocity is known.

Legend: ✅ provided in the base repository · ⬜ to implement

---

## Phase 0 — Foundations (Week 0, 2–3 days)

| # | Task | Status |
|---|---|---|
| 0.1 | Create GitHub repo from this base; enable branch protection on `main` (PR + CI required) | ⬜ |
| 0.2 | Copy `.env.example` → `.env`; obtain Claude API key; create fine-grained GitHub token (read-only Actions + Contents) | ⬜ |
| 0.3 | Create a **demo target repo** with deliberately breakable CI (missing dependency, failing test, Dockerfile COPY error, YAML error) — this is your test bed and your interview demo | ⬜ |
| 0.4 | `./scripts/dev.sh up` and confirm `/healthz`, `/readyz` and dashboard load | ⬜ |
| 0.5 | Decide cloud: **Azure or AWS** (pick one; record it as ADR-002) | ✅ AWS (ECS Fargate + ECR) |

**Exit criteria:** stack runs locally; CI passes on first PR.

---

## Phase 1 — Working AI engineering assistant (Weeks 1–4) → `v0.1`

### Sprint 1 (Weeks 1–2): Repository intelligence + log diagnosis

| # | Task | Status |
|---|---|---|
| 1.1 | Domain model: Repository, Analysis, PipelineRun, Diagnosis, ProposedFix, AuditEvent | ✅ |
| 1.2 | `repo_analyzer`: languages, frameworks, manifests, Docker/CI/K8s detection, risk flags | ✅ |
| 1.3 | `log_processing`: secret redaction, failure-window extraction, heuristic classifier | ✅ |
| 1.4 | `claude_client`: forced tool use, timeouts, retries, token + latency capture | ✅ |
| 1.5 | `diagnoser`: grounding check, confidence cap, deterministic risk, offline fallback | ✅ |
| 1.6 | `POST /api/diagnose-log` + dashboard Diagnose page | ✅ |
| 1.7 | Add Alembic and replace `create_all` with migrations | ⬜ |
| 1.8 | Extend analyzer: Java/Go manifests, lockfile detection, test-framework detection | ⬜ |

### Sprint 2 (Weeks 3–4): GitHub integration + review loop

| # | Task | Status |
|---|---|---|
| 1.9 | `github_client`: repo metadata, failed runs, failed jobs, job logs | ✅ (verify against your demo repo) |
| 1.10 | `GET /api/repositories/{id}/runs` — list failed runs from GitHub in the dashboard | ⬜ |
| 1.11 | Diagnoses list + detail page backed by DB (currently only ad-hoc diagnose) | ⬜ |
| 1.12 | Approve / reject UI wired to `POST /api/fixes/{id}/decision` | ⬜ (API ✅) |
| 1.13 | "Explain this file" and "Generate tests for this function" endpoints (Claude, read-only) | ⬜ |
| 1.14 | Grow `evals/cases` to ≥ 15 real failures from your demo repo; record baseline accuracy | ⬜ (3 seed cases ✅) |
| 1.15 | Simple auth (GitHub OAuth or a single admin login) so reviewer identity is real | ⬜ |

**Exit criteria / demo:** break the demo repo → paste or select the failed run → see category,
root cause, verified evidence, proposed patch, risk badge → approve → event appears in audit trail.

---

## Phase 2 — Automation and DevOps (Weeks 5–8) → `v0.2`

| # | Task | Status |
|---|---|---|
| 2.1 | Multi-stage, non-root Dockerfiles; Compose stack with healthchecks and limits | ✅ |
| 2.2 | GitHub Actions: ruff, pytest + coverage, pip-audit, frontend type-check/build, image build | ✅ |
| 2.3 | Trivy image scan and kubeconform manifest validation in CI | ✅ (tighten: fail on CRITICAL) |
| 2.4 | **Check runner**: worker launches a throwaway container to run ruff/pytest/eslint/pip-audit on a cloned repo; stores results | ⬜ |
| 2.5 | **Webhook**: `POST /api/webhooks/github` (signature-verified) on `workflow_run` = failure → auto-diagnose | ⬜ |
| 2.6 | Publish images to GHCR (or ACR/ECR) on merge to `main`; tag with git SHA | ⬜ |
| 2.7 | Bash/Python dev tooling: `dev.sh` ✅; add `db-backup.sh`, `seed-demo.sh`, `rotate-logs` via logrotate | ⬜ |
| 2.8 | Linux VM deployment: `vm-bootstrap.sh` ✅ → Caddy/Nginx TLS, systemd unit for compose, ufw, non-root deploy user, SSH keys only | ⬜ |
| 2.9 | CD job: on tag, SSH to VM → pull images → `docker compose up -d` → smoke test `/readyz` | ⬜ |
| 2.10 | Runbook: "VM is down", "worker stuck", "Claude API errors" | ⬜ |

**Exit criteria / demo:** push a failing commit to the demo repo → webhook fires → diagnosis appears
on the public VM URL without manual action.

---

## Phase 3 — Production engineering (Weeks 9–12) → `v1.0`

| # | Task | Status |
|---|---|---|
| 3.1 | Kubernetes base manifests: probes, requests/limits, non-root, read-only FS | ✅ |
| 3.2 | Convert to Helm chart with `values-dev.yaml` / `values-prod.yaml` | ⬜ |
| 3.3 | Provision AKS **or** EKS + managed Postgres + managed Redis (Terraform preferred; portal/CLI acceptable with documented steps) | ⬜ |
| 3.4 | Secrets via Azure Key Vault / AWS Secrets Manager CSI driver; remove plain K8s Secret | ⬜ |
| 3.5 | Ingress + TLS (cert-manager); HPA on API | ⬜ |
| 3.6 | Observability: `/metrics` (Prometheus), dashboards for diagnosis latency, token cost per day, failure categories, approval rate; ship JSON logs to Azure Monitor / CloudWatch | ⬜ |
| 3.7 | AI reliability: per-repo daily token budget, circuit breaker on Claude errors, prompt caching for the system prompt, prompt version stored on each diagnosis | ⬜ |
| 3.8 | Evals in CI: run harness against FakeClaude on every PR; nightly against real Claude with a cost cap | ⬜ |
| 3.9 | Approved fix → open PR on new branch via GitHub App (`contents:write`, `pull_requests:write` only) | ⬜ |
| 3.10 | Deployment assistant: generate Dockerfile / K8s manifest for a profiled repo; validate with hadolint + kubeconform before showing | ⬜ |
| 3.11 | Documentation: SAFETY.md threat model (STRIDE), deployment procedure, ADRs, architecture diagrams, 3-minute demo video | ⬜ |

**Exit criteria / demo:** public HTTPS URL on Kubernetes; Grafana/Azure Monitor dashboard showing
real metrics; one approved fix opened as a PR end-to-end.

---

## Requirement traceability (Arimac posting)

| Requirement | Where it is demonstrated |
|---|---|
| Python, JavaScript, TypeScript | FastAPI backend; React + TypeScript dashboard |
| Bash / Python scripting for automation | `scripts/*.sh`, `evals/run_evals.py`, check runner (2.4) |
| AI fundamentals | Structured outputs, grounding check, evaluation metrics, confidence calibration, cost/latency trade-offs |
| Responsible use of AI tools such as Claude | Redaction, approval gates, deterministic risk, audit trail; also document how you used Claude Code while building it |
| Docker | Multi-stage non-root images, Compose stack, sandboxed check runner |
| Kubernetes | Manifests with probes/limits/security context → Helm → AKS/EKS |
| Linux ecosystem | VM bootstrap, systemd, ufw, logrotate, permissions, process troubleshooting |
| Azure or AWS | Managed cluster, managed DB/Redis, secrets manager, monitoring |
| Analytical thinking / problem solving | CI root-cause analysis, eval accuracy tracking, runbooks |
| Communication (technical + non-technical) | Architecture docs, ADRs, incident-style diagnosis summaries, README, demo video |

## Gaps the project cannot close

- **6 months of internship experience** is a separate requirement; this project complements it but
  does not substitute for it.
- **Cloud cost:** managed Kubernetes + managed DB costs money. Use free-tier credits, scale to zero
  after demos, and record the teardown procedure.
- **Claude API cost:** budget the nightly eval run and set a hard monthly spend limit on the key.
