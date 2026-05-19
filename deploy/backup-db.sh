#!/usr/bin/env bash
# backup-db.sh — dump Postgres horodaté dans /opt/lrtime/backups/
# À mettre en cron : 0 3 * * *  /opt/lrtime/deploy/backup-db.sh
set -euo pipefail
cd "$(dirname "$0")/.."

set -a; source .env.production; set +a
BACKUP_DIR="${BACKUP_DIR:-/opt/lrtime/backups}"
mkdir -p "$BACKUP_DIR"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$BACKUP_DIR/lrtime-$STAMP.sql.gz"

docker compose -f deploy/docker-compose.prod.yml --env-file .env.production \
  exec -T db pg_dump -U "${POSTGRES_USER:-lrtime}" "${POSTGRES_DB:-lrtime}" \
  | gzip > "$OUT"

echo "✅ Backup : $OUT"

# Rétention 14 jours
find "$BACKUP_DIR" -name "lrtime-*.sql.gz" -mtime +14 -delete
