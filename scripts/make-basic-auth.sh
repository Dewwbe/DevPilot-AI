#!/usr/bin/env bash
# Print the DEVPILOT_BASIC_HASH line for .env (bcrypt via Caddy). Usage: ./scripts/make-basic-auth.sh
set -euo pipefail
read -rsp "Dashboard password: " pw; echo
hash=$(docker run --rm caddy:2-alpine caddy hash-password --plaintext "$pw")
echo "Add to .env (single quotes keep the \$ characters literal):"
echo "DEVPILOT_BASIC_HASH='$hash'"
