#!/usr/bin/env bash
# Developer helper: ./scripts/dev.sh {up|down|test|lint|logs}
set -euo pipefail
cd "$(dirname "$0")/.."

case "${1:-}" in
  up)   [ -f .env ] || cp .env.example .env; docker compose up --build -d ;;
  down) docker compose down ;;
  test) (cd backend && pytest -q) ;;
  lint) (cd backend && ruff check .) && (cd frontend && npm run lint) ;;
  logs) docker compose logs -f --tail=100 "${2:-api}" ;;
  *) echo "usage: $0 {up|down|test|lint|logs [service]}"; exit 1 ;;
esac
