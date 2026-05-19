#!/usr/bin/env bash
# logs.sh — suivi des logs en temps réel
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -f deploy/docker-compose.prod.yml --env-file .env.production logs -f --tail=200 "$@"
