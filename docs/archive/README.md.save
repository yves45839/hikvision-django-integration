```bash
nano README.md
```

Puis colle tout ce qui suit 👇

---

# 🚀 Hikvision Django SaaS Platform

Plateforme SaaS multi-clients permettant :

* 🔐 Connexion des appareils Hikvision via ISUP (Device Gateway)
* 🏢 Gestion multi-tenant
* 🖥 Enregistrement automatique des devices par numéro de série (SN)
* 📡 Synchronisation temps réel avec Hik Device Gateway
* 🐳 Déploiement via Docker
* 🌐 API REST sécurisée

---

# 🧠 Architecture

```
Devices Hikvision (ISUP 5.0)
        │
        │  (Port 7660)
        ▼
Hik Device Gateway (VPS)
        │
        │  (API ISAPI)
        ▼
Django SaaS API (Docker)
        │
        ▼
PostgreSQL
```

---

# 🏗️ Stack Technique

* Python 3.12
* Django 5 / Django REST Framework
* PostgreSQL
* Docker & Docker Compose
* Hik Device Gateway v1.8+
* ISUP 5.0 Protocol
* Nginx (reverse proxy recommandé en prod)

---

# 🏢 Multi-Tenant Logic

Chaque client (tenant) possède :

* Un `code` unique
* Une liste de devices revendiqués
* Un espace logique isolé en base

## Device Claim Flow

1. Le client saisit le **SN réel** de son appareil dans l’interface SaaS
2. Le device est créé en statut `PENDING`
3. L’appareil se connecte au Gateway (ISUP)
4. Django synchronise avec Gateway
5. Si le SN correspond → statut `ACTIVE`

---

# 📦 Installation

## 1️⃣ Cloner le projet

```bash
git clone git@github.com:yves45839/hikvision-django-integration.git
cd hikvision-django-integration
```

---

## 2️⃣ Configuration environnement

Créer `.env` :

```bash
cp .env.example .env
nano .env
```

Exemple :

```
DJANGO_DEBUG=1
DJANGO_SECRET_KEY=change-me
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,213.156.133.202

DB_NAME=saas
DB_USER=saas
DB_PASSWORD=saas
DB_HOST=db
DB_PORT=5432

HIKGW_BASE_URL=http://host.docker.internal:88
HIKGW_USER=admin
HIKGW_PASS=your_password
```

---

## 3️⃣ Lancer la stack

```bash
docker compose up -d --build
```

---

## 4️⃣ Migrations

```bash
docker compose exec web python manage.py migrate
```

---

## 5️⃣ Créer un superuser

```bash
docker compose exec web python manage.py createsuperuser
```

---

# 🔐 Configuration des Devices Hikvision

Sur l’appareil :

* ISUP Enabled
* Server IP → IP publique du VPS
* Port → `7661`
* Device ID → SN réel
* Encryption Key → clé configurée côté Gateway et device

---

# 📡 Synchronisation Gateway

## Endpoint interne

```
POST /api/hikgateway/sync-devices/
```

Fonction :

* Appelle ISAPI `deviceList`
* Récupère `serial`, `devIndex`, `status`
* Met à jour les devices Django

---

# 🗂️ Structure Projet

```
/tenants
/devices
/events
/core
/docker-compose.yml
/.env.example
```

---

# 🗃️ Modèle Device

```python
class Device(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    serial = models.CharField(max_length=100, unique=True)
    dev_index = models.CharField(max_length=64, unique=True, null=True)
    status = models.CharField(max_length=30)
    protocol = models.CharField(max_length=50, default="ISUP5.0")
    created_at = models.DateTimeField(auto_now_add=True)
```

---

# 🔄 Device Lifecycle

| Status  | Description                            |
| ------- | -------------------------------------- |
| PENDING | SN enregistré mais pas encore connecté |
| ACTIVE  | Device online et validé                |
| OFFLINE | Déconnecté du gateway                  |

---

# 🌍 Déploiement Production

## Recommandé :

* HTTPS via Nginx / Traefik
* Reverse proxy unique port 443
* Gateway port 7660 exposé
* Celery pour sync automatique
* Logs centralisés

---

# 🛡️ Sécurité

* Un device ne peut appartenir qu’à un seul tenant
* Validation SN unique globale
* Auth JWT pour API
* Webhook Gateway sécurisé (HMAC recommandé)
* Variables sensibles via `.env`

---

# 🔄 Roadmap

* [ ] Sync automatique toutes les 30 secondes
* [ ] Webhook temps réel Gateway
* [ ] Dashboard tenant
* [ ] Monitoring device health
* [ ] Streaming proxy intégré
* [ ] Billing multi-tenant

---

# 📘 API Principales

### Claim Device

```
POST /api/devices/claim/
{
  "serial": "FN2090414"
}
```

### List Devices

```
GET /api/devices/
```

### Sync Gateway

```
POST /api/hikgateway/sync-devices/
```

---

# 👨‍💻 Auteur

Yves
Projet SaaS Hikvision Multi-Tenant
Côte d’Ivoire 🇨🇮

---

# 📜 Licence

Propriétaire – Tous droits réservés.

---

# 🎯 Vision

Créer une plateforme SaaS sécurisée permettant :

* Déploiement massif de terminaux Hikvision
* Gestion centralisée multi-entreprises
* Intégration temps réel
* Modèle économique scalable


