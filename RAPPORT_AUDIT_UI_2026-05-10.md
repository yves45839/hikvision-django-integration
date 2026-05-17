# Audit UI navigateur LR Time — 2026-05-10

> Audit fonctionnel manuel piloté via Chrome MCP, sur l'instance locale lancée par `setup-and-start.bat` (Backend Django sur :8000, Frontend Next.js 16 + Turbopack sur :3000).
>
> Compte utilisé : `admin@hq-casa.test` / `Admin@2024` (tenant_admin créé par `create_demo_tenant`). Tenant actif : `hq-casa-2`.

---

## 1. Verdict

| Page | URL | État | Problème |
|---|---|---|---|
| Login | `/login` | ✅ | Login JWT fonctionne, redirection `?next=` OK, toast "Connexion réussie" |
| Dashboard | `/` | ⚠️ | KPIs à 0, chart **fallback démo** ("DONNÉES RÉELLES INDISPONIBLES · RENDU DE STRUCTURE CONSERVÉ") |
| People (Personnes) | `/employees` | ✅ | Page rend correctement, KPIs + filtres + empty state, badge "DONNÉES HIKCENTRAL EN DIRECT" |
| Planning | `/planning` | ✅ | Tabs Planning équipe/Calendrier/Emploi de temps/Quart, navigation semaine OK |
| Devices (Appareils) | `/devices` | ✅ | KPIs (0), filtres "Tous les types/tenants/liaisons", boutons Synchroniser/Ajouter par IP/Ajouter |
| Reports (Rapports) | `/reports` | ✅ | Filtres journalier/hebdo/mensuel, exports Excel/PDF/CSV, onglets RÉCAP / ARRIVÉES-DÉPARTS |
| Settings (Paramètres) | `/settings` | ⚠️ | Page rend, sections OK, mais **i18n incomplet** (titre `<h1>` toujours FR en mode EN) |
| Pricing | `/pricing` | ✅ | **Réparé** (fichier corrompu corrigé en v2). Empty state "Aucun plan configuré pour cette devise" |
| Billing | `/billing` | ❌ | **CRASH** : `Cannot read properties of undefined (reading 'gradient')` |
| i18n switch FR↔EN | header | ✅ | Toggle fonctionne. Sidebar, KPI labels, page chrome traduits |

---

## 2. Bugs critiques détectés

### 2.1 ❌ /billing crashe — `BillingOverview` plante sur mock vide

**Reproduction** : navigate to `http://localhost:3000/billing` après login → page d'erreur React :

> Une erreur est survenue
> Cannot read properties of undefined (reading 'gradient')

**Cause** dans `components/billing/billing-overview.tsx:88` :

```tsx
const plan = PLANS.find((p) => p.id === currentSubscription.planId)!
// …
<div className={cn("…", plan.gradient)}>   // ligne 135 — plan est undefined
```

`PLANS` vient de `lib/mock-data/demo-billing.ts:3` :

```ts
export const PLANS: Plan[] = []
```

Le tableau a été vidé (sans doute pour ne pas afficher de fausses données), mais le composant garde le non-null assertion `!` et déréférence directement `plan.gradient`. Résultat : crash dur dès qu'on charge la page.

**Fix recommandé** (1 ligne) :

```tsx
const plan = PLANS.find((p) => p.id === currentSubscription.planId)
if (!plan) {
  return <BillingEmptyState onUpgrade={() => onTabChange("plans")} />
}
```

Plus rigoureusement : remplacer la dépendance à `demo-billing` par les endpoints réels `/api/billing/summary/` + `/api/billing/plans/` qui existent déjà côté backend (cf. tests Phase 3.17 ajoutés en v2).

### 2.2 ❌ CORS — header `X-Tenant-Code` non listé dans `CORS_ALLOW_HEADERS`

**Reproduction** : exécutée via `javascript_tool` sur la page `/` après login :

```js
// Cas 1 — Authorization seul → 200 ✅
fetch('http://localhost:8000/api/employees/', {
  headers: { Authorization: 'Bearer …' }
})  // status: 200

// Cas 2 — Authorization + X-Tenant-Code → CORS preflight FAIL ❌
fetch('http://localhost:8000/api/employees/', {
  headers: { Authorization: 'Bearer …', 'X-Tenant-Code': 'hq-casa-2' }
})  // TypeError: Failed to fetch
```

**Cause** : `app/config/settings.py` ne définit **pas** `CORS_ALLOW_HEADERS`. La liste par défaut de `django-cors-headers` ne contient pas `X-Tenant-Code`, donc tout preflight `OPTIONS` qui mentionne ce header est rejeté côté navigateur.

**Conséquence** : tous les endpoints qui dépendent de `X-Tenant-Code` (par exemple `/api/billing/summary/`, et tous ceux protégés par `assert_can_manage_billing` ou `get_request_tenant`) échouent silencieusement côté front. C'est probablement la raison pour laquelle le Dashboard tombe en fallback "DONNÉES RÉELLES INDISPONIBLES".

**Fix recommandé** dans `app/config/settings.py` (juste après `CORS_ALLOWED_ORIGINS`) :

```python
from corsheaders.defaults import default_headers
CORS_ALLOW_HEADERS = list(default_headers) + ["x-tenant-code"]
```

### 2.3 ⚠️ i18n incomplet sur Settings (et probablement d'autres pages)

**Reproduction** : `localStorage.setItem('securepoint-locale', 'en')` puis recharger `/settings` :

- Header `OPERATIONAL SPACE / Settings / Tenant configuration, groups and security` → traduit ✅
- Boutons `Profile`, `Logout`, sélecteur `EN` → traduits ✅
- KPIs `1 TENANTS / 0 DEPTS / 0 GROUPES / 0 LECTEURS` → 2 traduits, 2 toujours en FR ⚠️
- `<h1>Paramètres</h1>` du corps + `Configuration globale : organisation, groupes d'accès, horaires, notifications et sécurité.` + sidebar `Sections / Organisation / Horaires / Sécurité / Notifications / Général` → **toujours en français** ❌

Le mix FR/EN est visible dans la même capture d'écran. Cela signifie que les composants à l'intérieur de `app/settings/page.tsx` n'utilisent pas les hooks i18n (`useTranslation` / `t(...)`). Le contexte `LanguageProvider` ne couvre que le chrome (header + sidebar).

**Fix** : ces strings doivent passer par `lib/i18n/context.tsx`. Ce n'est pas bloquant prod mais ça casse la promesse "FR + EN au lancement" du business plan LR Time.

---

## 3. Constats hors bug bloquant

### 3.1 Données : tout à 0 (DB vide hormis le tenant démo)

`create_demo_tenant` crée le tenant + admin + opérateur, mais ne crée **pas** d'employés, de devices ni d'événements. Donc tous les KPIs s'affichent à 0 et le Dashboard tombe sur sa courbe placeholder "structure conservée". C'est intentionnel d'après le code, mais ça veut dire qu'on ne peut pas auditer le rendu d'une vraie liste sans data.

**Suggestion** : enrichir `create_demo_tenant` pour pouvoir valider l'UI avec quelques fixtures (3 départements, 5 employés, 1 device, 20 events).

### 3.2 Auth & session

Session stockée dans `localStorage.securepoint-auth-session-v1` :

```
{
  user: { id, username, email, first_name, last_name, is_active },
  tokens: { access (232c JWT), refresh (233c) },
  tenants: [...],
  activeTenantCode: "hq-casa-2",
  lastLoginAt: "..."
}
```

Login flow propre. Pas vu de fuite de token dans la console.

### 3.3 Hot reload pendant l'audit

Plusieurs navigations ont été ralenties par "Compiling..." de Turbopack (Next 16). Dans un build prod (`npm run build && npm run start`), ces transitions seraient instantanées. Pas un bug, juste un constat utile pour le démarrage onboarding.

### 3.4 Le badge "1 Issue" en bas à gauche sur /billing

Next devtools indique 1 issue active sur la page erronée. Confirmation que c'est bien capté par les outils de dev.

---

## 4. Hiérarchie des bugs (ajout au rapport global)

### P0 — bloquant pré-commercialisation
1. **`/billing` crashe** dès qu'un user authentifié l'ouvre. C'est la page de monétisation principale. Cf. §2.1.
2. **CORS `X-Tenant-Code`** : tous les appels tenant-scopés depuis le navigateur échouent. Cf. §2.2.

### P1 — qualité visible
3. i18n incomplet sur Settings (et probablement Reports/People). Cf. §2.3.
4. `create_demo_tenant` ne crée pas de fixtures : l'app paraît morte au premier login.

### Inchangés depuis le rapport v2
- `pricing-page-client.tsx` : ✅ réparé, page `/pricing` se charge correctement
- Backend tests : 121/129 OK
- Bugs Celery + résilience non câblée : pas testés ici

---

## 5. Pages auditées avec captures (référence interne)

Les screenshots ne sont pas joints au markdown, mais étaient pris à chaque navigation :
1. `/login` — formulaire OK, toast "Connexion réussie"
2. `/` — Dashboard, KPIs, chart fallback démo, encart Hikvision droit
3. `/employees` — Personnes, KPIs, filtre Organisations, empty state
4. `/planning` — Tabs, semaine 19, empty state
5. `/devices` — KPIs, filtres, "AUCUN APPAREIL CONNECTÉ"
6. `/reports` — filtres + exports + onglets RÉCAP
7. `/settings` — i18n mix EN/FR (bug §2.3), 1 tenant, sections
8. `/pricing` — currency selector EUR/USD, empty state propre
9. `/billing` — **crash écran erreur**

---

## 6. Conclusion

L'application est **fonctionnellement utilisable pour 8 pages sur 9**. Le squelette de l'UI est solide, les pages sans données ont toutes des empty states propres, l'i18n switch FR↔EN fonctionne sur la coquille, et la page Pricing — réparée en v2 — se rend correctement.

**Deux blocages avant déploiement** :
1. Réparer `BillingOverview` (1 ligne, ~5 minutes).
2. Ajouter `X-Tenant-Code` dans `CORS_ALLOW_HEADERS` (3 lignes, ~5 minutes).

Avec ces deux fixes, l'app est prête pour une démo client. Les autres points (i18n, fixtures démo) sont des polishes qualité qui peuvent attendre un sprint dédié.
