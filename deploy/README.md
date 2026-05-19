# `deploy/` — Stack beta production

Tout ce qu'il faut pour déployer LR Time sur un VPS Ubuntu.

| Fichier | Rôle |
|---|---|
| `docker-compose.prod.yml` | Stack complète : db + redis + web + frontend + catchup + nginx + certbot |
| `.env.production.example` | Template d'environnement à copier en `.env.production` et remplir |
| `nginx.conf` | Reverse proxy HTTPS final (utilisé une fois le cert obtenu) |
| `nginx-bootstrap.conf` | Reverse proxy HTTP-only pour le 1er challenge Let's Encrypt |
| `frontend.Dockerfile` | Image Next.js production |
| `install-vps.sh` | Provisionne un VPS Ubuntu vide (Docker, ufw, fail2ban, user) |
| `generate-secrets.sh` | Génère les secrets crypto (Postgres, Django, Fernet, webhooks) |
| `bootstrap-tls.sh` | Premier certificat HTTPS (à lancer une seule fois) |
| `start.sh` / `stop.sh` / `logs.sh` | Opérations courantes |
| `create-superuser.sh` | Crée le compte admin Django |
| `backup-db.sh` | Dump Postgres horodaté (à mettre en cron) |

👉 **Guide pas-à-pas complet : voir [`../DEPLOY_BETA.md`](../DEPLOY_BETA.md)**

---

## TL;DR (utilisateur déjà familier)

```bash
# Sur ta machine
scp deploy/install-vps.sh root@VPS:/root/
ssh root@VPS bash /root/install-vps.sh

# Sur le VPS
sudo -iu lrtime
cd /opt/lrtime
bash deploy/generate-secrets.sh        # copie la sortie dans .env.production
nano .env.production                   # remplir DOMAIN, ALLOWED_HOSTS, EMAIL_*, etc.
bash deploy/bootstrap-tls.sh           # premier cert Let's Encrypt
bash deploy/start.sh                   # stack up
bash deploy/create-superuser.sh        # compte admin
```
