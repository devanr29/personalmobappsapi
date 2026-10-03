#!/usr/bin/env bash
# Nightly Postgres backup. Cron example (03:00 every day):
#   0 3 * * * /home/devanr2911/apps/nocturne/deploy/backup.sh >> /home/devanr2911/backups/backup.log 2>&1
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
cd "$REPO_DIR"

OUT="$BACKUP_DIR/nocturne-$(date +%F).dump"
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$OUT.tmp"
mv "$OUT.tmp" "$OUT"

find "$BACKUP_DIR" -name 'nocturne-*.dump' -mtime +"$KEEP_DAYS" -delete
echo "$(date '+%F %T') backup ok: $OUT ($(du -h "$OUT" | cut -f1))"
