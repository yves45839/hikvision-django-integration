#!/usr/bin/env bash
# =============================================================================
# generate-secrets.sh — Génère DJANGO_SECRET_KEY, KMS_KEY, POSTGRES_PASSWORD
# et les imprime tels quels (à coller dans .env.production).
#
# Nécessite python3 + openssl (les deux sont installés par install-vps.sh).
# =============================================================================
set -euo pipefail

echo "# === Secrets générés — copie dans .env.production ==="
echo
echo "POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -d '\n=' | head -c 40)"
echo
echo "DJANGO_SECRET_KEY=$(python3 -c 'import secrets,string; chars=string.ascii_letters+string.digits+"!@#%^&*(-_=+)"; print("".join(secrets.choice(chars) for _ in range(64)))')"
echo

# Fernet key (utilise cryptography si dispo, sinon fallback en base64 url-safe 32 octets)
if python3 -c "import cryptography.fernet" 2>/dev/null; then
  echo "KMS_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
else
  echo "KMS_KEY=$(python3 -c 'import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
fi
echo
echo "HIK_GATEWAY_WEBHOOK_TOKEN=$(openssl rand -hex 24)"
echo "PAYMENT_WEBHOOK_TOKEN=$(openssl rand -hex 24)"
