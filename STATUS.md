# STATUS — Hikvision Django Integration

> Audit : **2026-05-06** · Critère unique : **chaque page frontend doit marcher de bout en bout pour la logique de pointage** (sync events Hik → présence/rapport visible utilisateur).
>
> ✅ fonctionnel · ⚠️ partiel · ❌ absent

---

## 1. Verdict

**La chaîne pointage est fonctionnelle côté code applicatif.** Toutes les pages frontend sont branchées sur de vrais endpoints backend qui existent. Il reste deux maillons d'**infra/automatisation** à câbler pour que le pointage tourne tout seul en production.

| Page frontend | Front | Endpoint backend | État |
|---|---|---|---|
| Dashboard | ✅ agrège 5 endpoints client-side | events, reports/attendance, employees, devices, leaves | ✅ |
| Employés | ✅ | `/api/employees/` | ✅ |
| Planning | ✅ | `/api/plannings/`, `/api/leave-requests/` | ✅ |
| Devices | ✅ avec fallback démo | `/api/hikgateway/devices/`, `/api/devices/`, `/api/devices/onboard/` | ✅ |
| Rapports | ✅ | `/api/hikgateway/reports/attendance/` | ✅ |
| Configuration | ✅ | `/api/tenants/`, settings | ✅ |

> Le fallback `DEMO_DEVICES_DATA` / `mock-data.ts` n'est **pas** un mock primaire : c'est un filet de sécurité utilisé seulement quand l'API échoue. Pages branchées en mode normal.

---

## 2. Ce qui reste à faire pour que le pointage tourne tout seul

### P0 — Automatisation pointage (bloquants production)
1. **Celery + Beat** : créer `app/config/celery.py`, ajouter services `worker` et `beat` dans `docker-compose.yml`, planifier la mgmt command `hik_catchup_acs_events` toutes les 30 s par tenant actif. Aujourd'hui les events Hik ne remontent que si quelqu'un appelle manuellement `/api/hikgateway/catchup-acs-events/` ou la mgmt command.
2. **Câbler la résilience Hik** : `app/hik_gateway/services/gateway_connection.py` doit faire passer ses appels par `resilient_gateway_call(...)`. Sinon le module `app/hik_gateway/resilience.py` est code mort et les appels gateway sont nus (pas de retry, pas de circuit breaker).

### P1 — Qualité avant prod
3. Tests isolation multi-tenant (Phase 4.2 du BACKLOG, jamais faite).
4. Tests Stripe (Phase 3.17, jamais faits).
5. Compléter handlers webhook Stripe : `customer.subscription.{created,updated,deleted}`, `invoice.{paid,payment_failed,upcoming}` + sync `Tenant.is_active`.
6. Migrer `onboarding.schedule_job` du `threading.Thread` (`app/devices/services/onboarding.py:233`) vers Celery.

### P2 — Reste de la commercialisation
Phase 3 Stripe restante (feature gating, quotas, trial/dunning, TVA, PDF facture, coupons), Phase 9 (wizard, sample data, SSO), Phase 12 (squash migrations, backups Postgres, E2E Playwright, load test). Voir `BACKLOG.md`.

---

## 3. État backend par module

| Module | État | Note |
|---|---|---|
| `tenants/` | ✅ | auth JWT, signup B2B, GDPR (export/delete/DPA/consent log) |
| `audit/` | ✅ | |
| `employees/` | ✅ | biométrie chiffrée Fernet |
| `events/` | ✅ | scoping tenant corrigé 2026-05-06 |
| `devices/` | ⚠️ | onboarding via `threading.Thread` à migrer Celery |
| `hik_gateway/` | ⚠️ | services connection/payload OK, endpoints reports/events/devices/catchup tous présents, **résilience non câblée**, **catchup non Beat-planifié** |
| `billing/` (Stripe) | ⚠️ | modèles + checkout + portal + webhook URL ✅ ; handlers webhook squelette |
| `reports/` | — | dossier vide, **non utilisé** : les rapports vivent dans `hik_gateway` |
| `config/` | ⚠️ | settings/health/sentry ✅, **pas de Celery** |
| `tests/` | ⚠️ | 5 fichiers ; rien sur billing ni isolation tenant |

---

## 4. Endpoints backend utilisés par le frontend

> Vérifié 2026-05-06. Tous existent côté Django.

```
/api/auth/token/                       JWT
/api/auth/refresh/
/api/tenants/
/api/employees/                        + /:id/, search, departments, organisations
/api/plannings/  /api/planning-assignments/  /api/work-shifts/
/api/leave-requests/
/api/access-groups/
/api/devices/                          + /:id/, /:id/reboot/, /:id/config-page/
/api/devices/onboard/                  + /api/device-onboarding-jobs/
/api/hikgateway/devices/               liste devices côté gateway Hik
/api/hikgateway/events/                stream events (filtres tenant/dev/person/since_id)
/api/hikgateway/acs-events/            events ACS bruts
/api/hikgateway/catchup-acs-events/    POST manuel — à automatiser via Beat
/api/hikgateway/reports/attendance/    rapport présence (daily/weekly/monthly)
/api/hikgateway/attendance-corrections/        + /logs/
/api/hikgateway/sync-devices/
/api/hikgateway/read-card/
/api/hikgateway/register-webhooks/
/api/billing/checkout/subscription/    + /one-time/
/api/billing/portal/  /api/billing/webhook/  /api/billing/payment-intent/
/api/billing/plans/  /api/billing/subscriptions/  /api/billing/invoices/
/api/home/summary/                     summary public (anonyme)
/health/  /ready/                      healthchecks
/legal/tos/  /legal/privacy/           pages légales
```

---

## 5. Hygiène repo (fait 2026-05-06)

Archivé dans `docs/archive/` : `BACKLOG_PHASE6_11.md`, `EXECUTIVE_SUMMARY.txt`, `FILES_MANIFEST.txt`, `FILE_LISTING.txt`, `FINAL_REPORT.txt`, `IMPLEMENTATION_SUMMARY.txt`, `PHASE0_IMPLEMENTATION.md`, `PHASE6_11_README.md`, `README_PHASES6_11.txt`, `RISKS_AND_MITIGATIONS.md`, `lr-time-loaders.html`, `lr-time-metaball-contrast.html`, `README.md.save`, `frontend-mockup/`, `design-refonte-lr-time/`, `backend-dev.{err,out}.log`.

Racine actuelle : `README.md`, `AGENTS.md`, `BACKLOG.md`, `STATUS.md`, `requirements.txt`, `docker-compose.yml`, `Dockerfile`, `.env.example`, les 5 PDFs Hik, scripts `.bat`/`.ps1`, et les dossiers `app/`, `v0-secure-point-dashboard-design/`, `design-system/`, `postman/`, `email_previews/`, `docs/`.

---

## 6. Maintenance

À chaque fin de sprint : MAJ §1 et §3, ajouter une ligne au journal. Le `BACKLOG.md` reste roadmap, ce fichier reste vérité du code.

| Date | Auteur | Changement |
|---|---|---|
| 2026-05-06 | Yves + Claude | Création + audit corrigé : pages frontend toutes branchées, reports vit dans hik_gateway, scoping events corrigé, archive racine. |
