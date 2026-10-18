#!/usr/bin/env bash
# Seed a running stack for demos: connect the demo target repo and run one sample diagnosis.
# Usage: DEMO_REPO=owner/demo-repo [API_URL=http://localhost:8000] ./scripts/seed-demo.sh
set -euo pipefail

API_URL="${API_URL:-http://localhost:${API_PORT:-8000}}"
DEMO_REPO="${DEMO_REPO:?set DEMO_REPO=owner/repo (your demo target repository)}"
AUTH=()
[ -n "${BASIC_AUTH:-}" ] && AUTH=(-u "$BASIC_AUTH")  # user:password when behind Caddy basic auth

echo "==> waiting for $API_URL/readyz"
for _ in $(seq 1 30); do curl -fsS "$API_URL/readyz" >/dev/null 2>&1 && break; sleep 2; done

echo "==> connecting $DEMO_REPO"
code=$(curl -s -o /tmp/seed.out -w '%{http_code}' "${AUTH[@]}" -X POST "$API_URL/api/repositories" \
  -H 'Content-Type: application/json' -d "{\"full_name\": \"$DEMO_REPO\"}")
case "$code" in 201) echo "connected";; 409) echo "already connected";; *) cat /tmp/seed.out; exit 1;; esac

echo "==> sample diagnosis (missing dependency)"
curl -fsS "${AUTH[@]}" -X POST "$API_URL/api/diagnose-log" -H 'Content-Type: application/json' \
  -d '{"log": "Step 5/8 : RUN pip install -r requirements.txt\nERROR: No matching distribution found for foobarlib==9.9\nProcess completed with exit code 1."}'
echo
echo "Done. Next: add the webhook (docs/DEPLOY-VM.md) and break the demo repo's CI."
