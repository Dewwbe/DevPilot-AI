#!/usr/bin/env bash
# Dump the Postgres database to a gzip file and prune old dumps.
# Usage: ./scripts/db-backup.sh        (cron runs it nightly on the VM)
# Restore: gunzip -c FILE | docker compose exec -T postgres psql -U devpilot devpilot
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && { set -a; . ./.env; set +a; }

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETAIN_DAYS="${BACKUP_RETAIN_DAYS:-14}"
mkdir -p "$BACKUP_DIR"

out="$BACKUP_DIR/devpilot-$(date +%Y%m%d-%H%M%S).sql.gz"
tmp="$out.partial"
docker compose exec -T postgres pg_dump -U devpilot --no-owner devpilot | gzip > "$tmp"
[ -s "$tmp" ] || { rm -f "$tmp"; echo "backup is empty, aborting" >&2; exit 1; }
mv "$tmp" "$out"
echo "backup written: $out ($(du -h "$out" | cut -f1))"

find "$BACKUP_DIR" -name 'devpilot-*.sql.gz' -mtime +"$RETAIN_DAYS" -print -delete
