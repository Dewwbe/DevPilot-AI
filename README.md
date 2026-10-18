# DevPilot AI

AI-assisted platform that diagnoses failed CI/CD pipelines with Claude and proposes
evidence-backed fixes that a human must approve before anything changes.

- **Backend:** Python 3.12 · FastAPI · Celery · Redis · PostgreSQL · Claude API
- **Frontend:** React · TypeScript · Vite
- **Platform:** Docker · GitHub Actions · Kubernetes · Azure/AWS

## Quick start

```bash
cp .env.example .env            # add DEVPILOT_ANTHROPIC_API_KEY and DEVPILOT_GITHUB_TOKEN
./scripts/dev.sh up             # postgres, redis, api, worker, web
open http://localhost:8080      # dashboard
open http://localhost:8000/docs # OpenAPI
```

Without an API key, diagnosis falls back to the heuristic classifier (`model=heuristic`).

## Development

```bash
cd backend && pip install -e ".[dev]" && pytest && ruff check .
cd frontend && npm install && npm run dev      # http://localhost:5173, proxies /api
python evals/run_evals.py --mode fake           # offline evals (also: heuristic; real needs a key)
```

## How it stays safe

Secrets are redacted before any LLM call · a per-repo token budget and circuit breaker bound cost and outages · Claude's output is schema-constrained · cited evidence
must appear verbatim in the log · risk is scored by fixed rules, not the model · high-risk fixes
need a written justification · every action is audited · fixes become PRs, never direct pushes.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) (diagrams: Kubernetes layout, AI reliability, fix-to-PR flow)
- [Roadmap and phase plan](docs/ROADMAP.md)
- [Safety and threat model (STRIDE)](docs/SAFETY.md)
- [Architecture decision records](docs/adr/)
- Deploying: [ECS Fargate](docs/DEPLOY-AWS.md) · [Linux VM](docs/DEPLOY-VM.md) · [EKS + Helm](docs/DEPLOY-K8S.md)
- [Runbook](docs/RUNBOOK.md) · [Demo script](docs/DEMO.md) · [How AI tools were used](docs/AI-USAGE.md)
