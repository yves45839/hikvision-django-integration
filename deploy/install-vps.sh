#!/usr/bin/env bash
# =============================================================================
# install-vps.sh — Provisionnement d'un VPS Ubuntu 22.04 / 24.04 pour LR Time
#
# À exécuter UNE SEULE FOIS, en tant que root (ou via sudo) sur le VPS fraîchement
# loué chez LWS. Idempotent : peut être relancé sans casser un setup existant.
#
# Usage :
#   curl -fsSL https://raw.githubusercontent.com/.../install-vps.sh | bash
#   # ou
#   scp deploy/install-vps.sh root@VPS:/root/
#   ssh root@VPS bash /root/install-vps.sh
# =============================================================================
set -euo pipefail

APP_USER="lrtime"
APP_DIR="/opt/lrtime"
REPO_URL="${REPO_URL:-https://github.com/Label-CI/hikvision-django-integration.git}"

log() { echo -e "\033[1;34m[install]\033[0m $*"; }
fail() { echo -e "\033[1;31m[install][FATAL]\033[0m $*" >&2; exit 1; }

# ---- 0. Pré-checks ---------------------------------------------------------
[[ $EUID -eq 0 ]] || fail "Lance ce script en root (ou via sudo)."
. /etc/os-release
[[ "$ID" == "ubuntu" ]] || fail "OS détecté : $ID. Ce script vise Ubuntu."
log "Ubuntu $VERSION_ID détecté."

# ---- 1. Système ------------------------------------------------------------
log "Mise à jour du système..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
apt-get install -y \
  ca-certificates curl gnupg lsb-release \
  ufw fail2ban git make jq htop unattended-upgrades

# Mises à jour de sécurité auto
dpkg-reconfigure -f noninteractive unattended-upgrades

# ---- 2. Firewall + fail2ban ------------------------------------------------
log "Configuration du firewall (UFW)..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

log "Configuration fail2ban..."
systemctl enable --now fail2ban

# ---- 3. Docker -------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  log "Installation de Docker..."
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
else
  log "Docker déjà installé : $(docker --version)"
fi

# ---- 4. Utilisateur applicatif --------------------------------------------
if ! id "$APP_USER" >/dev/null 2>&1; then
  log "Création de l'utilisateur $APP_USER..."
  useradd --create-home --shell /bin/bash "$APP_USER"
  usermod -aG docker "$APP_USER"
else
  log "Utilisateur $APP_USER existe déjà."
  usermod -aG docker "$APP_USER" || true
fi

# ---- 5. Code applicatif ----------------------------------------------------
if [[ ! -d "$APP_DIR/.git" ]]; then
  log "Clone du repo dans $APP_DIR..."
  mkdir -p "$APP_DIR"
  chown "$APP_USER:$APP_USER" "$APP_DIR"
  sudo -u "$APP_USER" git clone "$REPO_URL" "$APP_DIR"
else
  log "Repo déjà cloné. Pull..."
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only || log "git pull non fast-forward — à régler à la main."
fi

# ---- 6. .env.production ----------------------------------------------------
ENV_FILE="$APP_DIR/.env.production"
if [[ ! -f "$ENV_FILE" ]]; then
  log "Copie de .env.production.example → .env.production"
  cp "$APP_DIR/deploy/.env.production.example" "$ENV_FILE"
  chown "$APP_USER:$APP_USER" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  log ""
  log "⚠️  ÉDITE $ENV_FILE AVANT DE LANCER LA STACK :"
  log "    - DOMAIN, ALLOWED_HOSTS, NEXT_PUBLIC_API_BASE_URL, CORS_ALLOWED_ORIGINS"
  log "    - POSTGRES_PASSWORD          (openssl rand -base64 32)"
  log "    - DJANGO_SECRET_KEY          (cf. DEPLOY_BETA.md)"
  log "    - KMS_KEY                    (Fernet — cf. DEPLOY_BETA.md)"
  log "    - EMAIL_* (Postmark/SES/SMTP)"
  log "    - HIK_DEVICE_GATEWAY_*"
  log ""
else
  log ".env.production existe déjà — laissé tel quel."
fi

# ---- 7. Résumé final -------------------------------------------------------
log "✅ Provisionnement terminé."
log ""
log "Étapes suivantes (à exécuter en tant que $APP_USER) :"
log "  sudo -iu $APP_USER"
log "  cd $APP_DIR"
log "  nano .env.production            # remplir les ???"
log "  bash deploy/bootstrap-tls.sh    # premier certificat Let's Encrypt"
log "  bash deploy/start.sh            # démarrer la stack complète"
log "  bash deploy/create-superuser.sh # créer ton compte admin"
log ""
