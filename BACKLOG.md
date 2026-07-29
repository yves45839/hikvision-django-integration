# Backlog de commercialisation — Pointage Hikvision SaaS

> **Format de case** : `[ ]` à faire · `[~]` rendu, en attente validation humaine · `[x]` validé.
> Seul l'humain coche `[x]`. Voir règles dans `AGENTS.md` (section Sprint Workflow). Le point 8 ne doit pas dépendre des autres sprint

## Phase 0 — Hardening de base

- [x] **0.1 — Secrets hors git** · `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` lus depuis env ; rotation `Lsg@2020` ; `.env.example` fourni ; secrets purgés de `docker-compose.yml`. Test : settings refuse de booter sans `SECRET_KEY` en prod.
- [x] **0.2 — Postgres branché** · `DATABASE_URL` câblé via `dj_database_url` dans `app/config/settings.py:117` ; docker-compose démarre sur Postgres réel. Test : `python manage.py migrate` sur Postgres vide passe.
- [x] **0.3 — Indexes critiques** · Indexes sur `AttendanceEvent(tenant, timestamp)`, `RawEvent(serial_no, occurred_at)`, etc. Test : migration appliquée, `EXPLAIN` vérifié.
- [x] **0.4 — Rate limiting** · `DEFAULT_THROTTLE_CLASSES` DRF + `django-axes` sur login/signup/OTP/reset. Test : 11ᵉ requête sur OTP renvoie 429.
- [x] **0.5 — Audit log** · Modèle `AuditEvent(actor, action, target, ip, ts)` ou `django-easy-audit`. Test : créer un device génère 1 ligne.
- [x] **0.6 — Chiffrement credentials device** · `Device.device_password`, `Device.ehome_key`, `DeviceOnboardingJob.*` chiffrés Fernet (`KMS_KEY` env). Test : round-trip + migration data.
- [x] **0.7 — JWT lifetime court + rotation** · Access 15 min, refresh 7j tournant, blacklist activée.
- [x] **0.8 — Headers sécurité** · HSTS, `SECURE_SSL_REDIRECT`, cookies `Secure`, `SECURE_PROXY_SSL_HEADER`. Test : `python manage.py check --deploy` clean.

## Phase 1 — Infra production

- [x] **1.1 — Dockerfile prod** · Multi-stage, gunicorn, user non-root, `HEALTHCHECK`.
- [x] **1.2 — Static files** · `whitenoise` + `STATIC_ROOT` + `collectstatic` dans entrypoint.
- [x] **1.3 — Healthchecks** · `/health/` (DB+cache) et `/ready/`.
- [x] **1.4 — Logging structuré + Sentry** · `LOGGING` JSON, `sentry-sdk[django]` avec tag `tenant_id`.
- [x] **1.5 — CI GitHub Actions** · Workflow lint+tests+coverage+build image.

## Phase 2 — Async & email

- [x] **2.1 — Celery + Redis + Beat** · Squelette + worker docker-compose ; tâche `ping` testée.
- [x] **2.2 — Email async** · `_send_auth_email` → tâche Celery avec retry exponential.
- [x] **2.3 — Push gateway async** · `_auto_sync_employees_queryset` → tâche Celery.
- [x] **2.4 — Onboarding async** · Remplacer `threading.Thread` (`app/devices/services/onboarding.py:233`) par Celery.
- [x] **2.5 — Catchup ACS planifié** · `hik_catchup_acs_events` → Celery Beat (toutes les 30 s par tenant actif).
- [x] **2.6 — Provider email pro** · `django-anymail` + Postmark/SES + templates HTML branded i18n FR/EN.

## Phase 3 — Stripe (cœur commercial)

- [ ] **3.1 — Modèles billing** · `Plan`, `Price`, `BillingCustomer`, `Subscription`, `Invoice`, `PaymentMethod`, FK `Tenant→Subscription`, champs `stripe_*_id`.
- [ ] **3.2 — SDK + settings** · `stripe>=10` ; `STRIPE_*_KEY`, `STRIPE_WEBHOOK_SECRET` ; cmd `seed_stripe_plans`.
- [ ] **3.3 — Checkout Session** · `POST /api/billing/checkout/` (auth + idempotency-key) → URL Stripe.
- [ ] **3.4 — Customer Portal** · `POST /api/billing/portal/`.
- [ ] **3.5 — Webhook signé** · `POST /api/billing/webhook/` avec `stripe.Webhook.construct_event` ; idempotence par `event.id`.
- [ ] **3.6 — Handler subscriptions** · `customer.subscription.{created,updated,deleted}` → sync `Subscription` + `Tenant.is_active`.
- [ ] **3.7 — Handler invoices** · `invoice.{paid,payment_failed,upcoming}` → persistance + `payment_status` enrichi.
- [ ] **3.8 — Feature gating** · Décorateur `@requires_plan_feature(...)` + middleware ; matrice plan→features.
- [ ] **3.9 — Quotas par plan** · `device_quota`, `employee_quota`, `org_quota`, `event_retention_days` lus depuis `Plan`.
- [ ] **3.10 — Trial 14 j** · `Subscription.trial_end` ; bannière backend ; expiration → désactivation.
- [ ] **3.11 — Dunning / grace** · `payment_failed` → grace 7j, lecture seule J+8, désactivation J+15.
- [ ] **3.12 — TVA UE** · Stripe Tax activé ; collecte VAT-ID B2B ; `Tenant.vat_id` validé.
- [ ] **3.13 — Facture PDF FR** · Numérotation séquentielle non-falsifiable, mentions légales, conservation 10 ans.
- [ ] **3.14 — Historique facturation** · `GET /api/billing/invoices/` paginé + URL PDF signée.
- [ ] **3.15 — Coupons / promo** · Endpoint `apply_coupon` ; relai Stripe Promotion Code.
- [ ] **3.16 — Suppression `payment-callback`** · Retirer `app/tenants/auth_views.py:565` au profit du webhook.
- [ ] **3.17 — Tests Stripe** · `stripe-mock` ou cassettes ; couverture des 6 events principaux + idempotence.

## Phase 4 — Multi-tenant durci

- [x] **4.1 — `TenantScopedManager`** · Manager générique ; refactor des viewsets non-scopés.
- [x] **4.2 — Tests isolation systématiques** · Pour CHAQUE viewset : tenant A ne voit/modifie pas ressources B (parametrize pytest).
- [x] **4.3 — Sécurité webhook Hik** · HMAC obligatoire (refus si token vide en prod), IP allowlist obligatoire.
- [x] **4.4 — `is_domain_verified` strict** · Refus boîtes publiques (gmail/outlook/yahoo) pour B2B ; flag `tenant_domain_kind`.
- [x] **4.5 — Bug events scoping** · Réviser `device__owner=user` (`app/events/views.py:21`) → logique tenant/org.

## Phase 5 — Sécurité avancée

- [x] **5.1 — 2FA TOTP** · `django-otp` + endpoint enroll/verify ; obligatoire pour `org_admin`.
- [x] **5.2 — Anti-bruteforce OTP** · Lock après 5 essais, expiration 10 min, log incident.
- [x] **5.3 — Session management** · "Mes appareils connectés" + révocation.
- [x] **5.4 — CSP + Permissions-Policy** · `django-csp` + headers durcis.

## Phase 6 — Conformité RGPD

- [x] **6.1 — Pages légales** · ToS, Privacy, Mentions, Cookies (markdown servi par template).
- [x] **6.2 — Export données (art. 20)** · `GET /api/auth/me/export/` → ZIP JSON + CSV.
- [x] **6.3 — Effacement (art. 17)** · `DELETE /api/auth/me/` → anonymisation + soft-delete tenant.
- [x] **6.4 — Consent log** · Modèle + capture au signup (ToS, Privacy, marketing) ; horodaté + IP.
- [x] **6.5 — Rétention configurable** · `event_retention_days` par plan ; cron de purge soft-delete + hard-delete.
- [x] **6.6 — DPIA biométrie** · Document interne + chiffrement fort `EmployeeFingerprint` / `EmployeeFace`.
- [x] **6.7 — DPA téléchargeable** · PDF généré et stocké au signup B2B.

## Phase 7 — Observabilité

- [x] **7.1 — Sentry tags** · `tenant_id`, `org_id`, `user_id`, `release` injectés.
- [x] **7.2 — Metrics Prometheus** · `django-prometheus` + métriques métier.
- [x] **7.3 — Dashboard interne** · Page admin "métriques globales" (MAU, MRR, churn 30j, signups).

## Phase 8 — Frontend (pages principales) — submodule `v0-secure-point-dashboard-design/`

> DoD pour chaque item de cette phase = **structure + visuel pro + connecté backend**.
> Branchement réel sur les endpoints DRF, plus de mocks.

- [~] **8.1 — Page Dashboard** · KPI temps réel, état présence du jour, alertes, derniers événements. Branché sur `GET /api/dashboard/...` (endpoints existants).
- [~] **8.2 — Page Employés** · Liste (search + filtres + pagination), fiche détail `/employees/[id]`, création/édition (modal ou page), suppression/désactivation. Branché sur `GET/POST/PATCH/DELETE /api/employees/`.
- [ ] **8.3 — Page Planning** · Vue semaine/mois des shifts, création/édition shift, congés visualisés. Branché sur `GET/POST /api/planning/...` et `/api/leaves/...`.
- [ ] **8.4 — Page Devices** · Liste devices, statut online/offline, détail device, ajout/onboarding. Branché sur `GET/POST /api/devices/`.
- [ ] **8.5 — Page Rapports** · Génération + téléchargement (PDF/Excel) des rapports présence, retards, anomalies. Branché sur `GET/POST /api/reports/...`.
- [ ] **8.6 — Page Configuration** · Profil tenant, organisations, utilisateurs internes, préférences (timezone, langue). Branché sur `GET/PATCH /api/tenants/...` et endpoints settings existants.

## Phase 9 — Onboarding & growth

- [ ] **9.1 — Wizard premier device** · Test connexion gateway live + diagnostic.
- [ ] **9.2 — Sample data** · Tenant fraîchement créé ⇒ données démo désactivables.
- [ ] **9.3 — SSO Google/Microsoft** · `django-allauth`.

## Phase 10 — Reporting avancé

- [ ] **10.1 — Rapports planifiés** · Beat : rapport mensuel envoyé par email (PDF + Excel).
- [ ] **10.2 — Connecteur paie** · Export normé Sage/PayFit/Lucca ; webhook sortant signé.

## Phase 11 — Résilience Hikvision

- [~] **11.1 — Retry + circuit breaker** · `tenacity` + `pybreaker` sur appels gateway.
- [~] **11.2 — Health monitoring devices** · Tâche périodique ping + status `online/offline`.
- [~] **11.3 — Dédup events robuste** · Clé `(serial_no, event_no, occurred_at)` ; tests collisions.

## Phase 12 — Pré-launch

- [ ] **12.1 — Squash migrations** · Avant GA, baseline propre.
- [ ] **12.2 — Backups Postgres** · `pg_dump` quotidien chiffré → S3 ; PITR documenté.
- [ ] **12.3 — Tests E2E** · Playwright : signup → checkout → device → rapport.
- [ ] **12.4 — Doc utilisateur** · Mini-site (Mintlify ou statique).
- [ ] **12.5 — Status page** · UptimeRobot ou statuspage.io.
- [ ] **12.6 — Load test** · k6 sur ingest webhook + reports (cible : 1k events/s).
- [ ] **12.7 — Audit sécurité externe** · Pentest ciblé (option fortement recommandée B2B).

## Phase 13 — Billing UI & i18n

> Anciens items 8.1–8.8. À démarrer **après la Phase 3 (Stripe backend)**.
> DoD = parcours utilisateur complet de bout en bout, branché Stripe live.

- [ ] **13.1 — Page pricing** · 3 plans + CTA Checkout.
- [ ] **13.2 — Bouton "S'abonner"** · Redirection Stripe Checkout (utilise 3.3).
- [ ] **13.3 — "Mon abonnement"** · Bouton Customer Portal (utilise 3.4).
- [ ] **13.4 — Bannière tenant** · États `trial`, `grace`, `failed`, `inactive`.
- [ ] **13.5 — Page facturation** · Historique factures + PDF (utilise 3.14).
- [ ] **13.6 — i18n FR/EN** · `next-intl` ou équivalent ; remplir les `.po` côté backend.
- [ ] **13.7 — Funnel signup** · signup → email verif → checkout → wizard premier device → 1er rapport.
- [ ] **13.8 — États erreur Stripe** · 3DS, SCA, carte refusée.

---

## Phase 14 — Pointage mobile géolocalisé

> App employé Expo (`mobile/`) + app Django `presence`. Positionnement v1 assumé :
> **contrôle de proximité, pas antifraude** (GPS client, drapeau `mocked` journalisé
> comme indice seulement).

- [~] **14.1 — Celery + Redis + Beat** · Infra async réelle (`config/celery.py`, services `worker`/`beat`) ; règle le P0 catchup : tâche beat `hik_catchup_all` toutes les 60 s avec verrou cache.
- [~] **14.2 — Rôle `employee` verrouillé** · `TenantRole.EMPLOYEE` (rang 5) ; scoping explicite `get_admin_tenant_ids` / `get_employee_tenant_ids` ; test-balai généré du routeur DRF (toute route non classifiée = échec).
- [~] **14.3 — Invitations mobiles** · `Employee.user` OneToOne ; `EmployeeInvitation` (token haché SHA-256, deep link `lrtime://`) ; accept = auto-login rôle employee, jamais de rétrogradation.
- [~] **14.4 — Sites de pointage** · `presence.Site` (lat/lng/rayon 30–2000 m) ; CRUD `punch-sites` audité ≥ org_admin ; onglet Réglages → Sites côté v0.
- [~] **14.5 — API punch géolocalisée** · Moteur pur `evaluate_mobile_punch` (inside/borderline/outside) ; heure serveur faisant foi ; idempotence par clé cliente (retry = même réponse 200) ; appareil virtuel par `kind`/capacités ; `source="mobile"` dans les rapports existants.
- [~] **14.6 — Rappels programmés** · Beat 60 s : avertissement T−15, rappel T+5 (masqué par un CHECK_IN dans la fenêtre du shift) ; `PunchReminderLog` unique = au-plus-une-fois avec rattrapage ; statuts par canal push/email/SMS ; réglages par tenant ; commande `send_punch_reminders --at --dry-run`.
- [~] **14.7 — App Expo** · Login, acceptation d'invitation (deep link), pointage GPS avec erreurs typées, historique, réglages FR/EN, push token par installation.
- [ ] **14.8 — SMS payant** · Brancher un vrai backend (`SMS_BACKEND` : stub Twilio fourni, Orange à écrire) + facturation du coût au tenant.
- [ ] **14.9 — Restriction site↔département** · Un site limité à certains départements/employés (v1 : tout site actif vaut pour tout le tenant).
- [ ] **14.10 — Rappels multi-créneaux** · Rappel de reprise après pause et second shift (v1 : premier créneau du jour uniquement).
- [ ] **14.11 — Durcissement antifraude** · Attestation d'intégrité (Play Integrity / DeviceCheck), détection mock avancée, biométrie au pointage.

---

## Légende & flux

```
[ ]  -> à faire
[~]  -> Claude a livré un patch / PR, en attente de validation humaine
[x]  -> humain a validé : Claude peut démarrer le sprint suivant
```

À chaque sprint clôturé, l'humain ajoute en fin de ligne : `— validé YYYY-MM-DD`.
