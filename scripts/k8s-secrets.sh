#!/usr/bin/env bash
# Create the devpilot-secrets Secret from the local .env (never commit .env).
set -euo pipefail
cd "$(dirname "$0")/.."
source .env
kubectl -n devpilot create secret generic devpilot-secrets \
  --from-literal=DEVPILOT_DATABASE_URL="$DEVPILOT_DATABASE_URL" \
  --from-literal=DEVPILOT_ANTHROPIC_API_KEY="$DEVPILOT_ANTHROPIC_API_KEY" \
  --from-literal=DEVPILOT_GITHUB_TOKEN="$DEVPILOT_GITHUB_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -
