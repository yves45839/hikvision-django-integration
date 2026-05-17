# Rapport de test LR Time — 2026-05-10

> Périmètre demandé : tests automatisés frontend + audit fonctionnel + couverture backend + frontend + intégration Hikvision.
> Méthode : exécution dans un sandbox Linux (Python 3.10 + Node 20 + npm). L'app n'a pas été démarrée sur la machine Windows ; l'audit "navigateur" a été remplacé par un test direct des endpoints HTTP du backend (`runserver` sandbox sur SQLite copié de `db.sqlite3`).

---

## 1. Verdict

| Volet | Statut | Score |
|---|---|---|
| Tests unitaires backend Django | Verts à 91 % | 84 / 92 OK |
| Tests automatisés frontend | **Aucun** runner configuré | 0 / 0 |
| Compilation TypeScript frontend | **Échec — fichier corrompu** | 12 erreurs TS, toutes dans 1 fichier |
| Démarrage backend (sandbox) | OK | runserver répond sur 127.0.0.1:8765 |
| Endpoints HTTP critiques | OK majoritairement, 2 anomalies | voir §4 |
| Intégration Hik Device Gateway | Code marche, mais résilience non câblée | confirme STATUS.md §2.1 et §2.2 |
| Migrations Django | À jour mais 1 migration oubliée | `hik_gateway` 0010 + altérations `billing` |

Le pointage applicatif est fonctionnel, conformément à STATUS.md. Les bloquants production listés dans STATUS.md (Celery/Beat, résilience non câblée) sont **toujours valides** au 2026-05-10. Un nouveau bloquant est apparu côté frontend (fichier `pricing-page-client.tsx` corrompu) — voir §3.2.

---

## 2. Backend Django — tests automatisés

Commande : `cd app && DATABASE_URL="" python manage.py test tests.<phase>` (SQLite en mémoire, sandbox Linux).

| Suite | Tests | Résultat |
|---|---|---|
| `tests.test_phase0` (sécurité, JWT, encryption Fernet, throttling) | 24 | OK |
| `tests.test_phase1` (auth, CORS, healthchecks, settings) | 27 | OK |
| `tests.test_phase11_resilience` (retry + circuit breaker isolés) | 11 | OK |
| `tests.test_phase6_rgpd` (export, suppression, DPA, consent log) | 11 | OK |
| `tests.test_phase7` (observabilité, métriques Prometheus, dashboard admin) | 19 | **1 FAIL + 7 ERRORS** |
| **Total** | **92** | **84 OK · 1 FAIL · 7 ERROR** |

### 2.1 Échec phase 7 — dashboard admin non routé en environnement de test

Tous les échecs phase 7 portent sur `AdminDashboardTests` et sur l'URL `/admin/dashboard/metrics/`.

```
FAIL: test_dashboard_accessible_to_staff (tests.test_phase7.AdminDashboardTests)
AssertionError: 404 not found in [200, 302]
```

- La vue `AdminDashboardView` est définie dans `app/config/admin_dashboard.py:15`.
- Mais elle n'est **routée nulle part** dans `app/config/urls.py`. Aucun `path("admin/dashboard/...")` dans le repo.
- Pourtant, sur le serveur runserver lancé en sandbox, `GET /admin/dashboard/metrics/` répond `302`. C'est l'admin Django qui intercepte le préfixe `/admin/` et redirige vers `/admin/login/` — l'URL n'est pas réellement servie par `AdminDashboardView`.
- Conclusion : la vue existe mais le câblage URL n'a jamais été fait ; le test passait peut-être historiquement avec un autre `urls.py` ou est mort-né.

**Action recommandée** : router explicitement `AdminDashboardView` dans `config/urls.py` avant `path("admin/", admin.site.urls)` et protéger par `staff_member_required`.

### 2.2 Migrations en attente (non bloquant mais à committer)

`python manage.py makemigrations --dry-run --check` détecte 2 migrations non générées :

- `hik_gateway/migrations/0010_rawevent_hik_gateway_dedupe__2df481_idx.py` — index sur `dedupe_key` du modèle `RawEvent`.
- `billing/` — multiples renames d'index + `Alter field` sur `Plan.is_metered`, `Plan.metered_unit_label`, `Subscription.stripe_subscription_item_id`, `UsageRecord.action`, `UsageRecord.timestamp`.

Cela signifie que les modèles ont été modifiés sans `makemigrations`. À régénérer + tester en CI.

### 2.3 Warnings à connaître

- 11 warnings `models.W042` (`Auto-created primary key used …`) sur `Device`, `DeviceOnboardingJob`, `DeviceOrganizationBinding`, `AttendanceEvent`, et tous les modèles `tenants/*`. Pas bloquant mais oblige à fixer `DEFAULT_AUTO_FIELD`.
- `RuntimeWarning: Model 'tenants.consentlog' was already registered` au boot — symptôme d'un import circulaire ou d'un double enregistrement (cf. l'historique de migrations `0007_delete_consentlog` + `0008_add_consentlog`).
- Dans `tests.test_phase6_rgpd`, deux `RuntimeWarning: DateTimeField received a naive datetime` (`EmailVerificationToken.used_at`, `PasswordResetToken.used_at`). À corriger via `timezone.now()`.

---

## 3. Frontend (Next.js 16 / React 19 / TS 5.7)

### 3.1 Aucun test automatisé configuré

`v0-secure-point-dashboard-design/package.json` contient seulement `dev / build / start / lint`. Aucun framework de test (Jest, Vitest, Playwright en runtime) :

- `@playwright/test` apparaît dans `package-lock.json` mais en dépendance transitive ; aucun `playwright.config.*` n'existe.
- Aucun fichier `*.test.*` ni `*.spec.*` dans le repo (hors `node_modules`).
- `npm run lint` échoue : `eslint: not found` — ESLint n'est pas listé dans `devDependencies`.

**Action recommandée** : ajouter Vitest + un Playwright minimal ; au minimum, ajouter `eslint` + `eslint-config-next` en devDependencies pour que `npm run lint` fonctionne.

### 3.2 Compilation TypeScript — **fichier corrompu (bloquant)**

`./node_modules/.bin/tsc --noEmit` retourne 12 erreurs, toutes dans **un seul fichier** :

```
components/billing/pricing-page-client.tsx
  342:1  TS1128 Declaration or statement expected
  342:2  TS1128 Declaration or statement expected
  343:9  TS1109 Expression expected
  344:7  TS1128 Declaration or statement expected
  374:7  TS2657 JSX expressions must have one parent element
  417:5  TS1128 Declaration or statement expected
  481:5  TS1005 'try' expected
  484:1  TS1128 Declaration or statement expected
  ...
```

Le fichier contient une portion de code dupliquée et tronquée. Aux lignes 341–344 :

```tsx
  } catch {
    return `${value.toFixed(2)} ${currency.toUpperCase()}`
  }
}
n}</p>          ← ligne 342, débris du composant inséré au mauvais endroit
        )}
      </div>
```

Et à partir de la ligne 478 le bloc `formatPrice` est ré-écrit, suivi par un fragment orphelin :

```tsx
  } catch {
    return `${value.toFixed(2)} ${currency.toUpperCase()}`
  }
}
t(value)        ← orphelin
  } catch {
    return `${value.toFixed(2)} ${currency.toUpperCase()}`
  }
}
```

**Conséquence directe** : `next build` casse et la page Pricing (publique) ne peut pas se compiler. À corriger d'urgence avant tout déploiement / démo.

**Action recommandée** : restaurer ce fichier depuis le dernier commit où il compilait (`git log --diff-filter=A -- components/billing/pricing-page-client.tsx` puis `git checkout <sha>~1 -- components/billing/pricing-page-client.tsx`), ou le réécrire depuis les composants voisins (`billing-plans.tsx`, `live-subscription-card.tsx`).

---

## 4. Endpoints HTTP — runserver sandbox

Backend lancé via `python manage.py runserver 127.0.0.1:8765 --noreload`, DB SQLite copiée de `app/db.sqlite3`.

| Endpoint | Attendu | Observé | Verdict |
|---|---|---|---|
| `GET /health/` | 200 | 200 | OK |
| `GET /ready/` | 200 | 200 | OK |
| `GET /legal/tos/` | 200 | 200 | OK |
| `GET /legal/privacy/` | 200 | 200 | OK |
| `GET /api/schema/` | 200 (OpenAPI JSON) | 200 | OK |
| `GET /api/schema/swagger-ui/` | 200 (UI Swagger) | **404** | Anomalie |
| `GET /api/billing/plans/` | 200 | 200 (`[]` — DB vide côté plans) | OK schéma, données absentes |
| `GET /api/devices/` (no auth) | 401 | 401 | OK |
| `GET /api/employees/` (no auth) | 401 | 401 | OK |
| `GET /api/hikgateway/devices/` (no auth) | 401 | 401 | OK |
| `POST /api/auth/token/` (no body) | 400 | 400 | OK |
| `POST /api/auth/signup/` | 200/201 ou 400 | **404** | Endpoint **n'existe pas sous ce path** |
| `POST /api/auth/client-signup/` | présent | présent (chemin réel via `tenants/auth_urls.py:25`) | OK — bien documenter le bon path |
| `GET /api/home/summary/` | "summary public (anonyme)" selon STATUS.md §4 | **401 Authentification requise** | Incohérence doc / code |
| `GET /admin/dashboard/metrics/` | 200/302 attendu par test_phase7 | 302 (admin login) — la vue elle-même non routée | Bug, voir §2.1 |
| `POST /api/hik/events` (webhook Hik) | 202 si auth/headers OK | 202 sur payload trivial | OK route, à valider en bout en bout |

### 4.1 OpenAPI / drf-spectacular — schéma incomplet

Au boot du runserver, drf-spectacular émet :

- 11 erreurs `unable to guess serializer` sur les vues `hik_acs_events_api`, `hik_attendance_corrections_api`, `hik_attendance_correction_logs_api`, `hik_catchup_acs_events_api`, `hik_devices_api`, `hik_events_api`, `hik_read_card_api`, `hik_register_webhooks_api`, `hik_attendance_reports_api`, `hik_sync_devices_api`, `home_summary_api`.
- Conséquence : ces endpoints sont absents (ou en fallback string) du schéma OpenAPI exposé. Un futur swagger / postman généré sera incomplet.
- Cause : ce sont des `@api_view` sans `serializer_class`. Soit annoter avec `@extend_schema(...)`, soit migrer vers des `GenericAPIView`.

### 4.2 Swagger UI 404

`/api/schema/swagger-ui/` répond 404. Soit `drf_spectacular.views.SpectacularSwaggerView` n'est pas câblé dans `urls.py`, soit l'URL diffère. Sans Swagger UI, la doc n'est pas explorable depuis un navigateur — alors que c'est utile pour les revendeurs / partenaires intégrateurs (point de la stratégie LR Time).

### 4.3 Incohérence `home_summary_api`

STATUS.md §4 décrit `/api/home/summary/` comme un *summary public (anonyme)*, mais le serveur retourne `401 — Informations d'authentification non fournies`. Soit le code a divergé de la doc, soit la permission par défaut DRF (`IsAuthenticated`) écrase l'intention. À trancher selon le besoin (page d'accueil publique → permission `AllowAny`).

---

## 5. Intégration Hik Device Gateway — vérification statique

### 5.1 ✅ Mgmt command catchup présent

`app/hik_gateway/management/commands/hik_catchup_acs_events.py` existe.

### 5.2 ❌ Pas de Celery (confirme STATUS.md §2 P0-1)

```
grep -rn "celery\|Celery\|@shared_task\|@app.task\|beat_schedule" config/ hik_gateway/ → 0 résultat
docker-compose.yml → aucun service "celery" / "worker" / "beat"
```

Le catchup Hik n'est planifié nulle part. Dans l'état, les events Hik n'arrivent dans la DB que si quelqu'un appelle manuellement `python manage.py hik_catchup_acs_events` ou `POST /api/hikgateway/catchup-acs-events/`. **Bloquant production** — pas de pointage automatique.

### 5.3 ❌ Résilience non câblée (confirme STATUS.md §2 P0-2)

```
grep -rn "resilient_gateway_call" --include="*.py"
hik_gateway/resilience.py:64:def resilient_gateway_call(...)
tests/test_phase11_resilience.py:13: from ... import resilient_gateway_call
tests/test_phase11_resilience.py:51: result = resilient_gateway_call(mock_func, "test-tenant")
… (uniquement dans le module et ses tests, jamais en runtime)
```

`hik_gateway/services/gateway_connection.py:36` retourne directement un `HikGatewayClient` ; `hik_gateway/client.py` fait des `requests.post / put / delete` nus, sans retry ni circuit breaker.

Le module `resilience.py` est testé en isolation (les 11 tests `test_phase11_resilience` passent), mais **rien ne l'utilise** sur le chemin de production. Dès que la gateway Hik (213.156.133.202:88 d'après `.env`) a un hoquet réseau, l'app tombe en cascade.

**Action recommandée** : envelopper dans `gateway_connection.py` (ou directement dans `HikGatewayClient`) chaque appel HTTP par `resilient_gateway_call(callable, tenant_code)`.

### 5.4 ⚠️ Onboarding via `threading.Thread`

`devices/services/onboarding.py:233` lance un `threading.Thread` pour traiter un `DeviceOnboardingJob` en arrière-plan. Sous Gunicorn multi-workers, ce thread est tué dès que le worker recycle. À migrer vers Celery (cf. §5.2).

---

## 6. Liste hiérarchisée des bugs / risques détectés

### P0 — bloquants pré-prod
1. **Frontend ne build plus** : `components/billing/pricing-page-client.tsx` est corrompu (12 erreurs TS, lignes 342, 343, 374, 417–419, 481, 484). Cf. §3.2.
2. **Pas de Celery / Beat** : les events Hik n'arrivent pas en continu. Cf. §5.2 et STATUS.md §2.
3. **Résilience Hik mort-née** : `resilient_gateway_call` jamais appelé hors tests. Cf. §5.3.

### P1 — qualité / cohérence
4. `AdminDashboardView` non routée → 1 FAIL + 7 ERRORS dans `test_phase7`. Cf. §2.1.
5. Migrations non générées (hik_gateway 0010 + altérations billing). Cf. §2.2.
6. `home_summary_api` exige l'auth alors que STATUS.md la donne publique. Cf. §4.3.
7. 11 vues `hik_gateway` + `home_summary_api` sans `serializer_class` → schéma OpenAPI incomplet. Cf. §4.1.
8. `/api/schema/swagger-ui/` → 404. Cf. §4.2.
9. Aucun test runner frontend (pas de Vitest, pas de Playwright config, pas d'eslint installé). Cf. §3.1.

### P2 — hygiène
10. 11 warnings `models.W042` à fixer via `DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'`.
11. `tenants.consentlog already registered` au boot — résidu de l'historique de migrations 0007/0008.
12. Datetime naïfs sur `EmailVerificationToken.used_at` et `PasswordResetToken.used_at`.
13. `onboarding.schedule_job` via `threading.Thread` à migrer Celery.

---

## 7. Ce que ce rapport ne couvre PAS

Pour transparence :

- Pas d'audit UI dans le navigateur. Le démarrage manuel sur Windows + parcours des 6 pages (Dashboard, Employés, Planning, Devices, Rapports, Configuration) prendrait plusieurs heures de pilotage à l'aveugle. Et de toute façon, le frontend ne builderait pas tant que `pricing-page-client.tsx` n'est pas réparé.
- Pas de test E2E contre la vraie gateway Hik (213.156.133.202:88) — pas eu d'accord explicite et l'IP est en production.
- Pas de test Stripe (déjà connu absent dans STATUS.md §2 P1-4).
- Pas de test d'isolation multi-tenant (déjà connu absent dans STATUS.md §2 P1-3).

Si tu veux que j'enchaîne sur l'un de ces points spécifiquement, dis-le moi.
