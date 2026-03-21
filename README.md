# Hikvision Django Integration

Backend Django/DRF pour piloter des équipements Hikvision via Hik Device Gateway, gérer des tenants, onboarder des devices, importer des employés et exploiter les événements de présence/contrôle d'accès.

Le dépôt contient aussi une interface frontend séparée dans `v0-secure-point-dashboard-design/`.

## Fonctionnalités couvertes

- Authentification JWT via `djangorestframework-simplejwt`
- API REST Django REST Framework
- Documentation OpenAPI via Swagger et ReDoc
- Gestion multi-tenant
- Gestion des devices Hikvision liés à un tenant
- Onboarding d'un device via la gateway partagée
- Synchronisation des devices depuis Hik Device Gateway
- Enregistrement des webhooks Hikvision
- Rattrapage des événements ACS (`catchup`)
- Gestion des employés, départements, organisations, plannings, shifts et groupes d'accès
- Rapports de présence agrégés par jour, semaine ou mois

## Architecture

```text
Terminaux Hikvision
        |
        |  ISUP / ISAPI
        v
Hik Device Gateway
        |
        |  HTTP API
        v
Django API (app/)
        |
        +--> SQLite par défaut (configuration actuelle)
        |
        +--> API DRF / JWT / Swagger
```

## Structure du dépôt

```text
.
|-- app/
|   |-- config/
|   |-- devices/
|   |-- employees/
|   |-- events/
|   |-- hik_gateway/
|   `-- tenants/
|-- postman/
|-- v0-secure-point-dashboard-design/
|-- Dockerfile
|-- docker-compose.yml
`-- requirements.txt
```

## Prérequis

- Python 3.12+
- Docker + Docker Compose si vous utilisez la stack conteneurisée
- Un accès à Hik Device Gateway si vous voulez tester l'intégration réelle

## Variables d'environnement utilisées

Le projet charge les variables depuis :

- `.env` à la racine du dépôt
- `app/.env`

Variables principales :

```env
ALLOWED_HOSTS=127.0.0.1,localhost
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

HIK_DEVICE_GATEWAY_BASE_URL=http://gateway-host:88
HIK_DEVICE_GATEWAY_USERNAME=admin
HIK_DEVICE_GATEWAY_PASSWORD=change-me

HIK_GATEWAY_WEBHOOK_TOKEN=
HIK_GATEWAY_ALLOWED_IPS=
HIK_WEBHOOK_IP=
HIK_WEBHOOK_PORT=443
HIK_WEBHOOK_URL=/api/hik/events
PAYMENT_WEBHOOK_TOKEN=

JWT_ACCESS_TOKEN_MINUTES=1440
JWT_REFRESH_TOKEN_DAYS=30
```

## Point important sur la base de données

La configuration Django actuelle utilise **SQLite** par défaut via `app/db.sqlite3`.

Le fichier `docker-compose.yml` démarre aussi un conteneur PostgreSQL, mais `DATABASE_URL` n'est pas exploité dans `app/config/settings.py` à l'heure actuelle. Le README documente donc le comportement réel du projet tel qu'il est aujourd'hui.

## Lancement en local

### 1. Installer les dépendances

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurer l'environnement

Créer un fichier `.env` à la racine ou dans `app/`, puis renseigner au minimum la connexion vers la gateway si vous voulez utiliser l'intégration Hikvision.

### 3. Appliquer les migrations

```bash
cd app
python manage.py migrate
```

### 4. Créer un superutilisateur

```bash
python manage.py createsuperuser
```

### 5. Démarrer le serveur

```bash
python manage.py runserver
```

API disponible par défaut sur [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Lancement avec Docker

```bash
docker compose up --build
```

Le service web est exposé sur le port `80`, donc l'API est accessible sur [http://localhost](http://localhost).

Le conteneur web exécute automatiquement :

- `python manage.py migrate`
- `python manage.py runserver 0.0.0.0:8000`

## Documentation API

- Swagger UI : [http://127.0.0.1:8000/api/docs/](http://127.0.0.1:8000/api/docs/)
- ReDoc : [http://127.0.0.1:8000/api/redoc/](http://127.0.0.1:8000/api/redoc/)
- Schéma OpenAPI : [http://127.0.0.1:8000/api/schema/](http://127.0.0.1:8000/api/schema/)

## Authentification

Obtenir un token :

```http
POST /api/auth/token/
Content-Type: application/json

{
  "username": "admin",
  "password": "mot-de-passe"
}
```

Rafraîchir un token :

```http
POST /api/auth/refresh/
```

## Endpoints principaux

### Ressources DRF

- `GET/POST /api/tenants/`
- `GET/POST /api/devices/`
- `GET/POST /api/events/`
- `GET/POST /api/employees/`
- `GET/POST /api/organizations/`
- `GET/POST /api/departments/`
- `GET/POST /api/plannings/`
- `GET/POST /api/work-shifts/`
- `GET/POST /api/access-groups/`

### Actions devices

- `POST /api/devices/onboard/`
- `GET /api/devices/{id}/config-page/`
- `POST /api/devices/{id}/add-persons/`
- `POST /api/device-onboarding-jobs/`
- `GET /api/device-onboarding-jobs/`
- `GET /api/device-onboarding-jobs/{id}/`
- `POST /api/device-onboarding-jobs/{id}/approve/`

Exemple d'onboarding :

```json
{
  "tenant_code": "tenant-a",
  "sn": "DS-K1T0001",
  "ehome_key": "1234567890ABCDEF1234567890ABCDEF",
  "dev_name": "Porte principale",
  "dev_type": "AccessControl",
  "device_username": "admin",
  "device_password": "change-me"
}
```

Exemple d'ajout de personnes sur un lecteur :

```json
{
  "employee_ids": [12, 18, 19],
  "include_cards": true,
  "stop_on_error": false
}
```

### Intégration Hik Gateway

- `GET /api/hikgateway/devices/`
- `POST /api/hikgateway/sync-devices/`
- `GET|POST /api/hikgateway/acs-events/`
- `POST /api/hikgateway/catchup-acs-events/`
- `POST /api/hikgateway/register-webhooks/`
- `GET /api/hikgateway/events/`
- `GET /api/hikgateway/reports/attendance/`
- `POST /api/hik/events`
- `POST /api/hikvision/events`

### Actions employees

Le module `employees` expose en plus plusieurs actions métiers, notamment :

- `POST /api/employees/{id}/push-to-gateway/`
- `GET /api/employees/{id}/schedule/`
- `POST /api/employees/{id}/move-department/`
- `POST /api/employees/{id}/assign-planning/`
- `POST /api/employees/{id}/assign-work-shift/`
- `POST /api/employees/{id}/assign-work-shifts/`
- `POST /api/employees/push-pending/`
- `POST /api/employees/import-from-gateway/`

Note push gateway:
- La cible des lecteurs est résolue automatiquement à partir de:
  - lecteurs liés directement à l'employé,
  - lecteurs hérités du département (selon le mode d'affectation),
  - lecteurs des groupes d'accès de l'employé (`access_groups.readers`).
- Les actions de mise à jour employé déclenchent désormais un push gateway automatique par défaut.
  - Pour différer la synchro, envoyer `push_now=false` dans le body de l'action concernée.

### Automatisation tenant et organisation

- `POST /api/auth/client-signup/`
- `POST /api/auth/verify-email/`
- `POST /api/auth/payment-callback/`
- `POST /api/auth/organizations/{organization_id}/invite/`
- `POST /api/auth/invitations/accept/`
- `GET /api/auth/me/organizations/`

Le flux couvre:

- creation automatique du tenant et d'une organisation par defaut
- verification email avec activation automatique du tenant (si les regles sont satisfaites)
- callback paiement optionnel pour finaliser l'activation
- invitations via lien magique avec roles `org_admin`, `operator`, `viewer`
- selection d'organisation limitee au scope utilisateur

Exemple de payload pour un job d'onboarding asynchrone:

```json
{
  "tenant_code": "tenant-a",
  "organization_id": 12,
  "sn": "DS-K1T0001",
  "ehome_key": "1234567890ABCDEF1234567890ABCDEF",
  "dev_name": "Porte principale",
  "dev_type": "AccessControl",
  "device_username": "admin",
  "device_password": "change-me"
}
```

## Commandes de management utiles

Depuis `app/` :

```bash
python manage.py hik_check_device --tenant tenant-a --serial DS-K1T0001
python manage.py hik_sync_devices --dispatch-core-devices
python manage.py hik_sync_devices --loop --interval 30 --dispatch-core-devices
python manage.py hik_register_webhooks --ip-address 1.2.3.4 --port 443 --url /api/hik/events
python manage.py hik_catchup_acs_events --max-results 50
```

## Flux d'utilisation recommandé

1. Créer un tenant.
2. Vérifier la connexion à la gateway.
3. Onboarder ou synchroniser les devices.
4. Enregistrer les webhooks sur les devices.
5. Importer ou créer les employés.
6. Pousser les employés vers les équipements si nécessaire.
7. Consulter les événements et les rapports de présence.

## Frontend séparé

Le dossier `v0-secure-point-dashboard-design/` contient une application Next.js indépendante.

Pour la lancer :

```bash
cd v0-secure-point-dashboard-design
npm install
npm run dev
```

Elle peut être connectée au backend via son fichier `.env.local`.

## Collections Postman

Le dossier `postman/` contient des collections utiles pour tester l'API.

## Limites et remarques actuelles

- `DEBUG=True` est actuellement défini directement dans `settings.py`.
- `SECRET_KEY` est codée en dur dans `settings.py`.
- La configuration PostgreSQL présente dans `docker-compose.yml` n'est pas branchée côté Django pour l'instant.
- Certains mots de passe/exemples présents dans les fichiers du dépôt doivent être remplacés avant tout usage en production.

## Licence

Aucune licence open source explicite n'est déclarée dans ce dépôt.
