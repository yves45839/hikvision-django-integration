# Pistes d'amélioration — Audit du 2026-07-28

Audit transversal du dépôt (backend Django, tests/CI, déploiement/infra), mené en trois passes parallèles. Les constats sont classés par gravité, avec références `fichier:ligne`, puis priorisés en fin de document.

**Vue d'ensemble** : la base est plus mûre que la moyenne — 303 tests (~8 000 lignes) avec une vraie couverture de l'isolation multi-tenant et de Stripe, un Dockerfile multi-stage non-root avec healthchecks, un runbook de déploiement documenté (`DEPLOY_BETA.md`), aucun secret réel commité. Les faiblesses se concentrent sur : (1) des trous de sécurité multi-tenant côté API et webhook, (2) une protection des données biométriques annoncée mais non branchée, (3) une absence totale de CI/lint malgré la suite de tests, (4) plusieurs bugs opérationnels qui casseront un déploiement frais.

---

## 🔴 Critique — Sécurité & multi-tenant

### 1. Webhook Hikvision ouvert par défaut
`app/hik_gateway/views.py:126-131` (`_is_allowed_ip`) et `:145-150` (`_is_allowed_token`) retournent `True` quand `HIK_GATEWAY_ALLOWED_IPS` / `HIK_GATEWAY_WEBHOOK_TOKEN` sont vides — leurs valeurs par défaut (`app/config/settings.py:289-290`). L'endpoint `hik_event_webhook` est `@csrf_exempt` et non authentifié : **sans configuration explicite, n'importe qui peut injecter des pointages**. En outre :
- `_client_ip()` (`views.py:119-123`) fait confiance au premier `X-Forwarded-For`, donc l'allowlist IP est contournable par simple en-tête forgé.
- La comparaison du token (`provided == expected`) n'est pas à temps constant.

**Correctif** : fail-closed (refuser si token/allowlist non configurés en prod), `hmac.compare_digest`, ne lire `X-Forwarded-For` que derrière un proxy de confiance.

### 2. Résolution d'appareil cross-tenant dans l'ingestion webhook
`app/hik_gateway/services/webhook_ingest.py:211-234, 419-434, 450-456` : si le webhook n'envoie pas `X-TENANT-CODE`, `tenant=None` et la recherche du `devIndex` se fait **dans toute la table Device, tous tenants confondus** ; l'événement est ensuite rattaché au tenant du device trouvé (`tenant_for_event = device.tenant`). Combiné au point 1, un `devIndex` connu ou deviné suffit à écrire un `AttendanceLog` (donnée de paie) dans le tenant d'un tiers, depuis Internet.

**Correctif** : tenant obligatoire sur le webhook (token par tenant ou binding device→tenant vérifié), interdire la résolution globale.

### 3. Création d'événements de présence non scopée
`app/events/views.py:10-21` : `AttendanceEventViewSet` est un `ModelViewSet` complet sans `perform_create`, et `app/events/serializers.py:4-7` expose `tenant` et `device` en **écriture**. La lecture est bien scopée (`scope_queryset_to_user_tenants`), mais `POST /api/events/` accepte n'importe quel tenant : tout utilisateur authentifié peut écrire des événements de présence chez un autre tenant.

**Correctif** : passer en `ReadOnlyModelViewSet`, ou `perform_create` avec contrôle de rôle et `tenant` read-only.

### 4. `TenantViewSet` en CRUD complet avec `IsAuthenticated` seul
`app/tenants/views.py:8-19` + `app/tenants/serializers.py:11-25` : aucun `perform_create`/`perform_update`, et le serializer expose en écriture `device_quota`, `payment_status`, `is_domain_verified`, `requires_manual_review`. Un simple membre `viewer` peut se passer `payment_status="paid"`, se mettre `is_domain_verified=True` (ce qui débloque l'auto-acceptation d'onboarding, cf. `app/devices/services/onboarding.py:19-24`) ou augmenter son quota d'appareils.

**Correctif** : restreindre à `TENANT_ADMIN`/staff ; champs de facturation/vérification en read-only côté API.

### 5. Toutes les écritures API accessibles au rôle `viewer`
`app/employees/views.py:181-186` : `_require_tenant_scope(..., minimum_role=TenantRole.VIEWER)` est la valeur par défaut, et tous les `perform_create`/`perform_update` (`:209, :241, :327, :357, :400, :494, :644, :1819`) l'utilisent sans élever le rôle. Idem `app/devices/views.py:126-131`. La hiérarchie `ROLE_RANK` (`app/tenants/services.py:7-12`) existe mais n'est jamais utilisée pour différencier lecture et écriture : un `viewer` peut créer/modifier/supprimer employés, plannings, groupes d'accès et appareils.

De plus, `DeviceViewSet` n'a **pas de `perform_update`** : `PUT/PATCH` ne vérifie ni le changement de `tenant` (contrairement à `employees/views.py:653-656`) ni le rôle, et `device_username`/`device_password` sont modifiables par tout membre.

**Correctif** : `OPERATOR` minimum pour les écritures, `ORG_ADMIN`/`TENANT_ADMIN` pour les suppressions ; ajouter `perform_update` sur `DeviceViewSet`.

### 6. `DEBUG=True` par défaut
`app/config/settings.py:52` : `DEBUG = _env_bool("DJANGO_DEBUG", True)`, et `docker-compose.yml:35` fixe `DJANGO_DEBUG: ${DJANGO_DEBUG:-1}`. Oublier `DJANGO_DEBUG=0` en déploiement :
- désactive tout le bloc `if not DEBUG` (`settings.py:259-265` : HSTS, `SECURE_SSL_REDIRECT`, cookies secure, `SECURE_PROXY_SSL_HEADER`) ;
- fait renvoyer **le token de vérification e-mail et le code OTP de reset de mot de passe dans la réponse HTTP** (`app/tenants/auth_views.py:307-309, 453-454, 521-522`) ;
- sert les tracebacks complets (settings, env) sur le port 80 exposé par le compose racine.

**Correctif** : défaut `False` (fail-closed), et un check de démarrage refusant `DEBUG=True` si `ALLOWED_HOSTS` contient autre chose que localhost.

---

## 🔴 Critique — RGPD / données biométriques

### 7. Le chiffrement biométrique est du code mort
`app/employees/biometric_encryption.py` n'est **importé nulle part** (vérifié par grep sur tout le dépôt). `EmployeeFingerprint.template` (`app/employees/models.py:845`) et `EmployeeFace.face_data` (`:863`) sont de simples `TextField` en clair. Pire : `_get_cipher_suite()` lit `settings.ENCRYPTION_KEY`, un réglage **qui n'existe pas** dans `config/settings.py` — la branche de repli génère une clé aléatoire à chaque appel, donc tout ce qui serait chiffré serait immédiatement indéchiffrable.

**Correctif** : brancher réellement le chiffrement (comme `Device.device_password_encrypted`) ou supprimer le module ; définir `ENCRYPTION_KEY` avec échec au démarrage si absent en prod.

### 8. Templates biométriques et PIN exposés sur `/api/employees/`
`app/employees/serializers.py:148-150, 178-180` : `fingerprints` et `face` sont imbriqués dans `EmployeeSerializer`. Un `GET /api/employees/` renvoie tous les templates d'empreintes et images de visage en base64, plus `pin_code` (`models.py:700`), à tout membre du tenant y compris `viewer` — et sans pagination (voir point 13).

**Correctif** : retirer ces champs de la liste, les servir via des sous-endpoints à rôle élevé et journalisés.

### 9. Chiffrement des mots de passe d'appareil défaillant en silence
`app/devices/encryption.py:11-14` : clé de repli en dur `b"dev-key-32bytes-change-in-prod!!"` si `KMS_KEY` est absent (défaut `""`, `settings.py:256`). Et `:21-25` : `encrypt_value` attrape **toute** exception et retourne la valeur **en clair**, stockée telle quelle sans aucune trace. Incohérence : `Gateway.password` (`app/hik_gateway/models.py:11`) est stocké en clair sans passer par ce mécanisme.

**Correctif** : échec explicite si `KMS_KEY` manque en prod, suppression du fallback silencieux, même traitement pour `Gateway`.

### 10. Fuites dans les logs et traçabilité RGPD lacunaire
- `app/hik_gateway/views.py:211` : le corps brut du webhook (numéros de badge, `employeeNo`) est loggé en `INFO` à chaque événement, sans redaction ; il est aussi persisté intégralement dans `RawEvent.payload` sans politique de rétention.
- `app/audit/utils.py:17` : `audit_log()` n'est appelé qu'**une seule fois** dans tout le code de production (`devices/views.py:148`). Aucune trace pour création/suppression d'employés, changements de rôles, corrections de pointage, accès aux données biométriques.
- `app/devices/services/onboarding.py:224-229` : `job.error_message = str(exc)` expose via l'API tenant l'URL interne de la gateway et jusqu'à 1 000 caractères du corps de réponse (`client.py:38-44`).

---

## 🟠 Bloquant — Déploiement

### 11. Sous-module frontend fantôme : un clone frais ne peut pas builder
`v0-secure-point-dashboard-design` est commité comme gitlink (`160000 680dd34...`) mais **`.gitmodules` n'a jamais existé dans l'historique** — `git submodule status` échoue, et le répertoire arrive vide sur tout clone frais. `deploy/install-vps.sh` fait un `git clone` simple, puis `deploy/docker-compose.prod.yml` builde `frontend` avec `context: ../v0-secure-point-dashboard-design` → `deploy/start.sh` échoue. `start-all.bat`/`setup-and-start.bat` cassent aussi.

**Correctif** : commiter un `.gitmodules` correct + `--recurse-submodules` dans les scripts, ou intégrer le frontend au monorepo.

### 12. `deploy/_active-nginx.conf` tracké mais réécrit par `bootstrap-tls.sh`
`bootstrap-tls.sh` (phase 4) fait `cp deploy/nginx.conf deploy/_active-nginx.conf` alors que le fichier est **tracké** (avec le contenu bootstrap HTTP-only) : le working tree du VPS est en permanence sale, `git pull --ff-only` (`install-vps.sh` étape 5) refuse. Et un `git checkout --` du fichier remettrait silencieusement la conf bootstrap qui répond `200 'bootstrap en cours'` sur toutes les routes — panne totale déguisée en déploiement réussi. Le `.gitignore` ignore `_active-nginx.conf.bak` mais pas le fichier lui-même.

**Correctif** : `git rm --cached deploy/_active-nginx.conf` + ajout au `.gitignore`.

### 13. Renouvellement certbot sans reload nginx → expiration TLS garantie
`deploy/docker-compose.prod.yml` : l'entrypoint certbot boucle sur `certbot renew` sans `--deploy-hook`, et nginx est un conteneur séparé que rien ne recharge — il gardera le certificat expiré en mémoire indéfiniment.

**Correctif** : cron hôte `docker compose exec nginx nginx -s reload` quotidien, ou deploy-hook + watcher.

### 14. `CSRF_TRUSTED_ORIGINS` absent
`SECURE_PROXY_SSL_HEADER` est défini (`settings.py:265`) mais `CSRF_TRUSTED_ORIGINS` n'existe nulle part : sur Django 4+, le login `/admin/` derrière le proxy HTTPS répondra 403 « Origin checking failed ». `deploy/create-superuser.sh` crée donc un admin qui ne peut pas se connecter.

**Correctif** : dériver de `ALLOWED_HOSTS`/`DOMAIN` (`https://…`).

### 15. Compose racine dangereux et IP publique en dur
`docker-compose.yml` : `ports: "80:8000"` + `restart: unless-stopped` + `DJANGO_DEBUG:-1` + `ALLOWED_HOSTS` défaut `213.156.133.202` (une IP publique réelle) + Redis publié `0.0.0.0:6379` **sans authentification** (vecteur RCE connu) + secrets avec défauts fonctionnels (`change_me_insecure_dev_only`). La même IP est figée dans `app/devices/models.py:19` comme `default` de champ **non éditable** (et dans la migration `0004`).

**Correctif** : renommer en `docker-compose.dev.yml`, binder sur `127.0.0.1`, retirer l'IP en dur (setting `DEVICE_DEFAULT_IP`), faire échouer le démarrage si les secrets manquent. Le fichier prod (`deploy/docker-compose.prod.yml`) est correct sur ces points.

---

## 🟠 Industrialisation

### 16. Aucune CI — alors que la suite de tests est le meilleur actif du dépôt
303 méthodes de test réparties sur 14 fichiers, avec une vraie couverture de l'isolation tenant (`app/tests/test_phase4_tenant_isolation.py`) et de Stripe mocké (`test_phase3_stripe.py`). Mais **aucun** `.github/workflows/`, gitlab-ci ou équivalent : rien ne les exécute automatiquement. `BACKLOG.md:23` coche pourtant « 1.5 — CI GitHub Actions » comme fait `[x]`. C'est le meilleur ratio valeur/effort du dépôt : ~30 lignes de workflow (tests sur service Postgres + build image).

### 17. Ni lint, ni format, ni lockfile, ni deps de dev
Aucun `pyproject.toml`, `ruff`, `black`, `mypy`, `pytest.ini`, `.pre-commit-config.yaml` — `AGENTS.md:41` waive explicitement le lint à chaque sprint. `requirements.txt` : 19 entrées toutes en planchers non bornés (`Django>=5.0`, `stripe>=10.0` — les majors Stripe cassent l'API) → deux builds Docker à un mois d'écart produisent des images différentes, sans CI pour le détecter. Aucun outil de dev déclaré ; le client `redis` manque alors que le service existe dans compose.

**Correctif** : pins `==` (ou `pip-compile`), `requirements-dev.txt`, `pyproject.toml` ruff+black, pre-commit.

### 18. Documentation en dérive (dans les deux sens)
- `BACKLOG.md:27` coche Celery+Redis+Beat comme fait : **aucun** `celery.py`, aucun import, pas de worker dans compose (`STATUS.md:29`, qui le liste en P0 bloquant, est exact).
- `STATUS.md` (par ailleurs excellent) est daté du 2026-05-06 et affirme à tort qu'il n'y a « rien sur billing ni isolation tenant » dans `tests/`.
- `AGENTS.md:4-6` : chemins Windows en dur (`C:\Users\PC MARKET\...`) et référence au « submodule » cassé (point 11).
- `README.md` n'explique nulle part comment lancer les tests.

### 19. Tests de résilience décoratifs — le code testé n'est pas branché
`app/tests/test_phase11_resilience.py` (11 tests) exerce `resilient_gateway_call` / circuit breaker de `app/hik_gateway/resilience.py`, mais `app/hik_gateway/services/gateway_connection.py` ne l'appelle **jamais** : `client.py:25,56,80,98` fait des `requests.post/put` bruts, sans retry, sans `requests.Session`, sans circuit breaker — avec le même bloc de gestion d'erreur copié-collé 5 fois. Le smoke test live (`app/scripts/smoke_test_hik_live.py:123-127`) greppe déjà ce problème et le signale.

**Correctif** : factoriser `client.py` en un `_request()` unique enveloppé par `resilient_gateway_call`.

### 20. Le chemin d'ingestion cœur est quasi non testé
`app/events/tests.py` : **1 seul test**. Dédup, ordre, timezones autour de `AttendanceEvent` n'ont pas de tests directs (couverture partielle indirecte via `hik_gateway/tests.py`). `BACKLOG.md:112` flagge d'ailleurs « 11.3 — Dédup events robuste » en `[~]`. Également peu couverts : `app/billing/services/usage.py` (report d'usage métré — là où vivent les bugs de double facturation), `app/billing/permissions.py`, `app/audit/`.

---

## 🟡 Qualité / performance / hygiène

### 21. N+1 massif sur la liste des employés
`app/employees/models.py:781-799` + `app/employees/schedule_resolver.py:34-40, 204-240` : les properties `effective_planning` / `effective_work_shift(s)` (exposées par le serializer) instancient un `ScheduleResolver` **par employé et par property**, chacun refaisant un `PlanningAssignment.objects.exists()` et remontant la chaîne `department.parent` non préchargée. `Employee.get_effective_devices` (`models.py:770-776`) fait des `order_by()` sur des relations préchargées, ce qui **annule** les `prefetch_related` de `views.py:619-628`. Sur 100 employés : au-delà du millier de requêtes.

**Correctif** : resolver unique par requête, cache de `_assignment_tables_available`, `select_related("department__parent")`, tri en Python sur les relations préchargées.

### 22. Écritures multi-modèles sans transaction
`app/employees/serializers.py:340-370` (`create`) et `:371-430` (`update`) : chaînes de créations (employé, cartes, empreintes, visage, M2M) sans `transaction.atomic()`. `update` fait `cards.all().delete()` puis `fingerprints.all().delete()` **avant** de recréer : une erreur au milieu laisse l'employé sans badge ni empreinte, donc sans accès physique. Même problème dans `views.py:92-140` (`_auto_sync_employees_by_ids`).

**Correctif** : `transaction.atomic()` + remplacement du delete-then-recreate par un diff.

### 23. `ConsentLog` déclaré trois fois
`app/tenants/models.py:210, 235, 265` : trois définitions successives de la même classe, avec des `Meta.indexes` et `on_delete` différents. Seule la dernière compte pour Django — les index de la version intermédiaire n'existent pas, et la lecture du fichier induit en erreur.

### 24. Architecture : fichier de vues géant, async par threads, Redis inutilisé
- `app/hik_gateway/views.py` : **3 094 lignes**, dont `hik_attendance_reports_api` = 782 lignes ; mélange vues HTML, API DRF, exports PDF/Excel/CSV, parsing XML. À éclater en `services/reports.py` + `services/exports.py`.
- Onboarding et catch-up utilisent des `threading.Thread(daemon=True)` bruts (`devices/services/onboarding.py:233-243`, `hik_gateway/views.py:262-287`) : perdus au redémarrage, sans retry, avec des verrous `set()` en mémoire inefficaces sous 4 workers gunicorn.
- Aucun `CACHES` configuré → `LocMemCache` par process : le throttling DRF (`settings.py:226-233`) est multiplié par le nombre de workers, et les cooldowns/verrous ne fonctionnent pas. Aucune pagination DRF par défaut. Les endpoints `AllowAny` de signup/OTP/reset (`tenants/auth_views.py:395, 458, 526`) n'ont pas de throttle dédié alors que l'OTP fait 6 chiffres.
- Redis est déjà dans compose : le brancher (cache + Celery/RQ) résout les trois points.

### 25. Hygiène du dépôt
- **7,6 Mo de PDF Hikvision à la racine** (5 fichiers, un seul commit `b82dd6c`) ≈ la quasi-totalité du poids de l'historique ; redistribution de docs constructeur au licensing incertain. → `docs/vendor/` + LFS, ou hors dépôt.
- Pas de **`.dockerignore`** : les PDF et `.git` partent dans le contexte de build, **deux fois** par `deploy/start.sh` (services `web` et `catchup`), sur un VPS de 2 Go.
- Rapports datés `RAPPORT_*.md`, transcript de chat `design-system/chats/chat1.md`, `email_previews/` générés : à déplacer vers `docs/archive/` (convention déjà établie) ou supprimer.
- Scripts Windows dupliqués (`start-local.bat` ≡ `start-local.ps1` ; `setup-and-start.bat` ⊇ `setup-deps.bat` + `start-all.bat`) avec un **bug** de parsing `.env` (`%%A:~0,1` n'est pas une syntaxe valide : les commentaires ne sont jamais filtrés) et des credentials de démo affichés en clair (`admin@hq-casa.test / Admin@2024`) — vérifier que `create_demo_tenant` refuse de tourner avec `DJANGO_DEBUG=0`.
- `Dockerfile` : `collectstatic || true` au build est un no-op qui masquerait une vraie erreur ; `deploy/generate-secrets.sh` imprime les secrets en clair dans le scrollback et tronque l'entropie du mot de passe Postgres (`tr -d '=' | head -c 40`).

---

## Priorisation recommandée

| # | Action | Points couverts | Effort |
|---|--------|-----------------|--------|
| 1 | Fermer le webhook : fail-closed token+IP, `compare_digest`, tenant obligatoire | 1, 2 | S |
| 2 | Scoper les écritures API : `events` en read-only, `TenantViewSet` restreint, rôles min. `OPERATOR`, `perform_update` devices | 3, 4, 5 | M |
| 3 | `DJANGO_DEBUG` défaut `False`, supprimer les défauts de secrets, compose racine assaini | 6, 15 | S |
| 4 | Retirer biométrie/PIN des serializers de liste, brancher le chiffrement, redaction des logs | 7, 8, 9, 10 | M |
| 5 | CI GitHub Actions (tests + build) — et réconcilier `BACKLOG.md` avec la réalité | 16, 18 | S |
| 6 | Réparer `.gitmodules` frontend + untracker `_active-nginx.conf` | 11, 12 | S |
| 7 | Deploy-hook certbot + `CSRF_TRUSTED_ORIGINS` | 13, 14 | S |
| 8 | Pins requirements + `requirements-dev.txt` + `pyproject.toml` (ruff/black) | 17 | S |
| 9 | Redis en cache backend + pagination DRF + throttles signup/OTP | 24 | M |
| 10 | `transaction.atomic()` + correction du N+1 employés | 21, 22 | M |
| 11 | Brancher `resilient_gateway_call`, factoriser `client.py`, tests `events/` | 19, 20 | M |
| 12 | Celery/RQ pour l'async, éclatement de `hik_gateway/views.py` | 24 | L |
| 13 | Hygiène dépôt : PDF hors racine, `.dockerignore`, scripts .bat consolidés | 25 | S |

Effort : S ≈ moins d'une journée · M ≈ 1-3 jours · L ≈ semaine+.

*Rapport généré par audit automatisé (Claude Code) le 2026-07-28. Les références fichier:ligne correspondent au commit `c84c104`.*
