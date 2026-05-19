#!/usr/bin/env bash
# =============================================================================
# start.sh — Démarrage / mise à jour de la stack beta LR Time
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

[[ -f .env.production ]] || { echo "❌ .env.production manquant"; exit 1; }

COMPOSE="docker compose -f deploy/docker-compose.prod.yml --env-file .env.production"

echo "[start] Build des images..."
$COMPOSE build --pull

echo "[start] Démarrage des services..."
$COMPOSE up -d

echo "[start] Attente que la stack soit healthy..."
sleep 10
$COMPOSE ps

echo ""
echo "✅ Stack en marche. Logs : bash deploy/logs.sh"
