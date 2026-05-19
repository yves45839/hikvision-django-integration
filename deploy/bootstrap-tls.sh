#!/usr/bin/env bash
# =============================================================================
# bootstrap-tls.sh — Premier certificat Let's Encrypt
#
# Préconditions :
#   - DNS A (et AAAA si IPv6) pointe DÉJÀ sur le VPS pour $DOMAIN
#   - .env.production rempli (DOMAIN, CERTBOT_EMAIL)
#   - Aucune autre conteneur n'utilise les ports 80/443
#
# Fonctionnement :
#   1. nginx en mode "bootstrap" (HTTP only) répond au challenge ACME
#   2. certbot récupère le certificat
#   3. on bascule sur nginx.conf normal (HTTPS)
#   4. on démarre la stack complète
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."  # racine du repo

[[ -f .env.production ]] || { echo "❌ .env.production manquant. Édite-le d'abord."; exit 1; }
set -a; source .env.production; set +a

: "${DOMAIN:?DOMAIN doit être défini dans .env.production}"
: "${CERTBOT_EMAIL:?CERTBOT_EMAIL doit être défini dans .env.production}"

COMPOSE="docker compose -f deploy/docker-compose.prod.yml --env-file .env.production"

echo "[bootstrap-tls] Cible : $DOMAIN — contact $CERTBOT_EMAIL"
echo "[bootstrap-tls] Vérification DNS..."
if ! getent hosts "$DOMAIN" >/dev/null; then
  echo "❌ $DOMAIN ne résout pas. Configure ton enregistrement DNS A puis relance."
  exit 1
fi

# 1. Démarrer nginx en mode bootstrap (HTTP only)
echo "[bootstrap-tls] Phase 1 — nginx HTTP only pour le challenge ACME..."
cp deploy/nginx-bootstrap.conf deploy/_active-nginx.conf

# On a besoin de db+web+frontend up car nginx les déclare en depends_on
$COMPOSE up -d db redis
sleep 5
$COMPOSE up -d web frontend
sleep 15
$COMPOSE up -d nginx
sleep 3

# 2. certbot via le réseau du compose
echo "[bootstrap-tls] Phase 2 — demande du certificat à Let's Encrypt..."
$COMPOSE run --rm --entrypoint "" certbot \
  certbot certonly \
    --webroot -w /var/www/certbot \
    --email "$CERTBOT_EMAIL" \
    --agree-tos --no-eff-email --non-interactive \
    -d "$DOMAIN"

# 3. Alias stable utilisé dans nginx.conf
echo "[bootstrap-tls] Phase 3 — lien symbolique stable /etc/letsencrypt/live/lrtime..."
$COMPOSE run --rm --entrypoint "" certbot \
  sh -c "rm -f /etc/letsencrypt/live/lrtime && ln -s /etc/letsencrypt/live/$DOMAIN /etc/letsencrypt/live/lrtime"

# 4. Bascule sur la vraie config nginx
echo "[bootstrap-tls] Phase 4 — bascule sur la config HTTPS..."
cp deploy/nginx.conf deploy/_active-nginx.conf
$COMPOSE restart nginx

echo ""
echo "✅ HTTPS actif sur https://$DOMAIN"
echo "   Lance maintenant : bash deploy/start.sh  (pour démarrer catchup + certbot auto-renew)"
