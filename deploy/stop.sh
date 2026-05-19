#!/usr/bin/env bash
# stop.sh — arrête la stack sans toucher aux volumes (les données restent)
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -f deploy/docker-compose.prod.yml --env-file .env.production down
echo "✅ Stack arrêtée. Données conservées dans les volumes."
