#!/usr/bin/env bash
# Deploy a tagged release on the VM: ./scripts/deploy.sh <image-tag>
# Pulls images, restarts the stack, smoke-tests /readyz and rolls back on failure.
# Reads REGISTRY / IMAGE_TAG / COMPOSE_FILE from .env in the repo root.
set -euo pipefail
cd "$(dirname "$0")/.."

NEW_TAG="${1:-${IMAGE_TAG:-}}"
[ -n "$NEW_TAG" ] || { echo "usage: $0 <image-tag>"; exit 1; }
[ -f .env ] || { echo ".env not found in $(pwd)"; exit 1; }

set -a; . ./.env; set +a
: "${REGISTRY:?REGISTRY missing in .env}"
PREV_TAG="${IMAGE_TAG:-}"

set_tag() {  # persist the tag so systemd restarts and manual `docker compose` use it
  if grep -q '^IMAGE_TAG=' .env; then sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=$1|" .env
  else echo "IMAGE_TAG=$1" >> .env; fi
  export IMAGE_TAG="$1"
}

smoke_test() {
  for _ in $(seq 1 30); do
    if docker compose exec -T api curl -fsS http://localhost:8000/readyz >/dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done
  return 1
}

case "$REGISTRY" in
  *.amazonaws.com*)  # ECR: needs the AWS CLI and an instance role / credentials with ECR read
    aws ecr get-login-password --region "$(echo "$REGISTRY" | cut -d. -f4)" \
      | docker login --username AWS --password-stdin "${REGISTRY%%/*}" ;;
esac

echo "==> backup before deploy (best effort)"
./scripts/db-backup.sh || echo "backup skipped"

echo "==> deploying $NEW_TAG (previous: ${PREV_TAG:-none})"
set_tag "$NEW_TAG"
docker compose pull
docker compose up -d --remove-orphans

echo "==> smoke test /readyz"
if smoke_test; then
  echo "==> deploy OK: $NEW_TAG"
  docker image prune -f >/dev/null
  exit 0
fi

echo "!! smoke test failed; recent api logs:"
docker compose logs --tail=40 api || true
if [ -n "$PREV_TAG" ] && [ "$PREV_TAG" != "$NEW_TAG" ]; then
  echo "==> rolling back to $PREV_TAG"
  set_tag "$PREV_TAG"
  docker compose up -d --remove-orphans
fi
exit 1
