# 🚀 LR Time — Guide de déploiement Beta (VPS LWS / Ubuntu)

> Objectif : mettre la beta publique en ligne en ~45 min sur un VPS Ubuntu LWS.
> Cible : **beta publique gratuite, Stripe désactivé, signup ouvert, HTTPS via Let's Encrypt.**

---

## 1. Prérequis

| Élément | Valeur |
|---|---|
| VPS | LWS Cloud / Ubuntu 22.04 LTS ou 24.04 LTS |
| RAM minimale | **2 Go** (4 Go recommandé pour build Next.js confortable) |
| Disque | 20 Go SSD |
| Accès | root via SSH (clé ou mot de passe) |
| Domaine | un sous-domaine ex. `app.lrtime.com` |
| DNS | enregistrement **A** vers l'IP publique du VPS (TTL court le temps de la beta) |
| Email | un compte SMTP transactionnel — **Postmark recommandé** (100 envois/jour gratuits, signup en 3 min) |

> ⚠️ **Avant de lancer le script** : crée l'enregistrement DNS A. Sans DNS qui résout, Let's Encrypt refusera d'émettre le certificat.

---

## 2. Étape 1 — Provisionnement du VPS (5-10 min)

Sur ta machine, copie le script d'install sur le VPS puis exécute-le :

```bash
scp deploy/install-vps.sh root@<IP_VPS>:/root/
ssh root@<IP_VPS> "bash /root/install-vps.sh"
```

Ce que le script fait, dans l'ordre :

1. `apt update && upgrade` + mises à jour de sécurité auto.
2. Pare-feu UFW : ouvre **22, 80, 443** uniquement.
3. Installe `fail2ban` (protection brute-force SSH).
4. Installe **Docker + docker compose plugin**.
5. Crée l'utilisateur `lrtime` (membre du groupe `docker`).
6. Clone le repo dans `/opt/lrtime` (variable `REPO_URL` modifiable).
7. Copie `deploy/.env.production.example` → `/opt/lrtime/.env.production` (chmod 600).

À la fin, le script affiche les commandes à exécuter ensuite.

---

## 3. Étape 2 — Configuration `.env.production` (5 min)

Connecte-toi en tant que l'utilisateur applicatif :

```bash
ssh root@<IP_VPS>
sudo -iu lrtime
cd /opt/lrtime
```

Génère les secrets cryptographiques :

```bash
bash deploy/generate-secrets.sh
```

Tu obtiens 5 lignes : `POSTGRES_PASSWORD`, `DJANGO_SECRET_KEY`, `KMS_KEY`, `HIK_GATEWAY_WEBHOOK_TOKEN`, `PAYMENT_WEBHOOK_TOKEN`. Copie-les telles quelles.

Édite ensuite le fichier :

```bash
nano .env.production
```

Champs **obligatoires** à remplir :

| Variable | Valeur |
|---|---|
| `DOMAIN` | `app.lrtime.com` (le tien) |
| `ALLOWED_HOSTS` | même domaine, séparés par virgule si plusieurs |
| `NEXT_PUBLIC_API_BASE_URL` | `https://app.lrtime.com` |
| `CORS_ALLOWED_ORIGINS` | `https://app.lrtime.com` |
| `FRONTEND_AUTH_BASE_URL` | `https://app.lrtime.com` |
| `CERTBOT_EMAIL` | `roland@label-ci.com` |
| `POSTGRES_PASSWORD` | sortie de `generate-secrets.sh` |
| `DJANGO_SECRET_KEY` | sortie de `generate-secrets.sh` |
| `KMS_KEY` | sortie de `generate-secrets.sh` |
| `EMAIL_HOST` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | clés Postmark (ou SMTP de ton choix) |

Champs **Hikvision** (`HIK_DEVICE_GATEWAY_*`) : si tu n'as pas encore de gateway publiquement accessible, mets des valeurs placeholder — tes beta-testeurs onboarderont leur propre gateway plus tard. Le reste de l'application tourne sans gateway active.

Sauvegarde et ferme (`Ctrl+O`, `Entrée`, `Ctrl+X`).

---

## 4. Étape 3 — Pointer le DNS et vérifier (≤ 5 min — selon ton registrar)

Chez ton registrar (LWS, OVH, etc.), crée :

```
Type: A
Nom:  app   (ou le sous-domaine voulu)
Valeur: <IP_VPS>
TTL: 300
```

Attends la propagation puis vérifie depuis le VPS :

```bash
getent hosts app.lrtime.com
# doit renvoyer l'IP de ton VPS
```

> Si ça ne résout pas encore, attends quelques minutes et relance.

---

## 5. Étape 4 — Premier certificat HTTPS (5 min)

```bash
cd /opt/lrtime
bash deploy/bootstrap-tls.sh
```

Ce script :

1. Démarre nginx en mode HTTP-only juste pour répondre au challenge ACME.
2. Demande le certificat à Let's Encrypt pour `$DOMAIN`.
3. Crée un alias `/etc/letsencrypt/live/lrtime/` pointant sur les certificats.
4. Bascule nginx sur la config HTTPS finale et redémarre.

Tu dois voir à la fin :

```
✅ HTTPS actif sur https://app.lrtime.com
```

---

## 6. Étape 5 — Démarrer la stack complète (5 min)

```bash
bash deploy/start.sh
```

Ce qui démarre :

| Service | Rôle |
|---|---|
| `db` | Postgres 16 (volume persistant `pgdata`) |
| `redis` | Cache + broker/résultats Celery |
| `web` | Django + gunicorn (3 workers) — migrations auto, collectstatic auto |
| `frontend` | Next.js 16 build production |
| `worker` | Celery worker — rattrapage Hikvision, rappels de pointage mobile, tâches async |
| `beat` | Celery Beat — planning statique (`hik-catchup-all` et `check-punch-reminders`, toutes les 60 s) |
| `catchup` | Boucle legacy `hik_catchup_acs_events` — redondante avec la tâche beat, à retirer après une semaine d'exécutions beat propres |
| `nginx` | Reverse proxy + TLS termination |
| `certbot` | Renouvellement auto du cert toutes les 12 h |

Vérifie l'état :

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file .env.production ps
```

Tous les services doivent être `Up (healthy)` au bout d'une minute.

---

## 7. Étape 6 — Compte admin (1 min)

```bash
bash deploy/create-superuser.sh
```

Renseigne email + mot de passe (ton compte `roland@label-ci.com`).

Vérifie :

```
https://app.lrtime.com/admin/   ← login Django admin
https://app.lrtime.com/         ← landing Next.js
https://app.lrtime.com/api/beta/info/   ← doit renvoyer { "beta_mode": true, ... }
```

---

## 8. Étape 7 — Backups automatiques (optionnel mais recommandé)

Active le cron de backup quotidien :

```bash
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/lrtime/deploy/backup-db.sh >> /var/log/lrtime-backup.log 2>&1") | crontab -
```

Les dumps `pg_dump` gzippés atterrissent dans `/opt/lrtime/backups/`, rétention 14 jours.

> Pour pousser hors-site (S3, R2…) : adapte `backup-db.sh` avec un `aws s3 cp` à la fin.

---

## 9. Vérifications post-déploiement

```bash
# Healthchecks
curl -s https://app.lrtime.com/health/   # doit renvoyer 200
curl -s https://app.lrtime.com/ready/    # doit renvoyer 200

# Beta info
curl -s https://app.lrtime.com/api/beta/info/

# Logs live
bash deploy/logs.sh

# Status containers
docker compose -f deploy/docker-compose.prod.yml --env-file .env.production ps
```

---

## 10. Opérations courantes

| Action | Commande |
|---|---|
| Démarrer / mettre à jour | `bash deploy/start.sh` |
| Arrêter (sans toucher aux données) | `bash deploy/stop.sh` |
| Logs en direct | `bash deploy/logs.sh` |
| Logs d'un service | `bash deploy/logs.sh web` |
| Shell Django | `docker compose -f deploy/docker-compose.prod.yml --env-file .env.production exec web python manage.py shell` |
| Migrations manuelles | `docker compose -f deploy/docker-compose.prod.yml --env-file .env.production exec web python manage.py migrate` |
| Mettre à jour le code | `git pull && bash deploy/start.sh` |
| Backup ponctuel | `bash deploy/backup-db.sh` |
| Renouveler cert manuellement | `docker compose -f deploy/docker-compose.prod.yml --env-file .env.production run --rm certbot renew` |

---

## 11. Sortie de beta (passage en GA)

Quand tu seras prêt à activer Stripe :

1. Crée tes plans dans Stripe Dashboard (test puis live).
2. Édite `.env.production` :
   - `BETA_MODE=0`
   - `STRIPE_SECRET_KEY=sk_live_...`
   - `STRIPE_PUBLISHABLE_KEY=pk_live_...`
   - `STRIPE_WEBHOOK_SECRET=whsec_...`
3. `bash deploy/start.sh`
4. Configure le webhook Stripe pour pointer vers `https://app.lrtime.com/api/billing/webhook/`.
5. Termine la **Phase 3** du `BACKLOG.md` (handlers webhook subscription/invoice, feature gating, dunning).

---

## 12. Troubleshooting

**Le frontend ne se construit pas (out of memory)**
→ VPS sous-dimensionné. Solutions :
- Builder l'image en local, push sur Docker Hub / GHCR, puis `docker pull` sur le VPS.
- Ou ajouter 2 Go de swap : `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`

**Let's Encrypt refuse le cert**
→ Vérifier `getent hosts $DOMAIN` côté VPS. DNS pas propagé ou pointant ailleurs.

**`/api/...` renvoie 502**
→ `docker compose ... logs web` — gunicorn n'a pas démarré (souvent migration échouée ou env var manquante).

**`/admin/` est sans CSS**
→ `docker compose ... exec web python manage.py collectstatic --noinput` puis `docker compose ... restart nginx`.

**Webhook Hikvision ne reçoit rien**
→ `HIK_GATEWAY_ALLOWED_IPS` filtre les IPs source. Mets l'IP publique de ta gateway ou vide la liste temporairement.

**Catchup ne tourne pas**
→ `docker compose ... logs catchup` — sans gateway accessible, la commande remontera des erreurs (normal en beta sans device).

---

## 13. Ce qui n'est PAS prêt pour la beta — à savoir

| Domaine | État | Impact beta |
|---|---|---|
| Celery + Beat propre | **en place** (`worker` + `beat`, planning statique) | La boucle `catchup` legacy reste une semaine en doublon, puis à retirer. |
| SMS de rappel de pointage | backend Noop par défaut (`SMS_BACKEND`) | Jamais gratuit — brancher Twilio/Orange plus tard si souhaité ; push + email actifs. |
| Résilience Hik (`resilient_gateway_call`) | non câblée | Si la gateway flanche, l'appel échoue sans retry. À surveiller. |
| Tests Stripe / isolation tenant | partiels | Sans impact tant que Stripe est off. |
| Squash migrations | non fait | OK pour beta. À faire avant GA. |
| Status page externe | absent | Acceptable. UptimeRobot peut être branché sur `/health/` en 2 min. |
| Load test | non fait | Beta = trafic faible. À refaire avant GA. |

Le reste (chiffrement Fernet, RGPD export/delete, audit log, 2FA, headers sécurité, signup B2B) est **déjà en place** et opérationnel.

---

## 14. Annonce publique de la beta

Suggestion de checklist pré-annonce :

- [ ] DNS résout, HTTPS valide (vérifie sur https://www.ssllabs.com/ssltest/)
- [ ] Inscription test depuis un device différent (pas le tien) fonctionne
- [ ] Email de vérification arrive en moins de 30 s
- [ ] Page `/admin/` accessible uniquement avec ton compte superuser
- [ ] Bandeau "Beta gratuite" visible sur le frontend
- [ ] `/api/beta/info/` renvoie `beta_mode: true`
- [ ] Backup quotidien en cron
- [ ] Sentry DSN renseigné (recommandé même en beta — tu veux les stack traces)
- [ ] Page de statut (UptimeRobot ou statuspage.io) configurée

---

**Auteur :** Label CI · LR Time team — `roland@label-ci.com`
**Maj :** 2026-05-18
