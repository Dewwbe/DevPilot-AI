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
cd backend && python ../evals/run_evals.py      # diagnosis accuracy
```

## How it stays safe

Secrets are redacted before any LLM call · Claude's output is schema-constrained · cited evidence
must appear verbatim in the log · risk is scored by fixed rules, not the model · high-risk fixes
need a written justification · every action is audited · fixes become PRs, never direct pushes.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap and phase plan](docs/ROADMAP.md)
- [Safety and threat model](docs/SAFETY.md)
- [Architecture decision records](docs/adr/)
