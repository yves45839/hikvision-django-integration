# Billing — Stripe integration

Cette app gère les abonnements SaaS, les paiements ponctuels, la facturation à
l'usage et le portail client Stripe pour la plateforme.

> **Mise à jour 2026-05-06** — ajout de l'essai gratuit 14 jours sans CB
> (`trial_period_days` + `trial_requires_card`) et du sélecteur multi-devise
> sur la page `/pricing`. Voir la section
> [« Essai gratuit & multi-devise »](#essai-gratuit--multi-devise) plus bas.

## Architecture

```
billing/
├── models.py              # Plan, Customer, Subscription, Invoice, Payment, UsageRecord, WebhookEvent
├── services/              # Couche d'abstraction du SDK Stripe
│   ├── stripe_client.py   # Initialise stripe.api_key
│   ├── customers.py       # get_or_create_customer(tenant)
│   ├── checkout.py        # Sessions Checkout (subscription + one-time) + Customer Portal
│   ├── payments.py        # PaymentIntent (Stripe Elements)
│   └── usage.py           # report_usage(subscription, quantity)
├── webhooks.py            # Handler des évènements Stripe (idempotent)
├── views.py               # Endpoints DRF
├── urls.py                # Routing /api/billing/...
├── serializers.py         # DTOs DRF
├── permissions.py         # Scoping par tenant
└── management/commands/
    └── sync_stripe_plans.py  # Synchronise le catalogue depuis Stripe
```

Stripe est la **source de vérité**. Les modèles locaux sont un cache + journal
d'audit pour que le dashboard puisse afficher les données sans appeler l'API
Stripe à chaque requête.

## Configuration

### 1. Installer la dépendance

```bash
pip install -r requirements.txt
```

(`stripe>=10.0` a été ajouté.)

### 2. Variables d'environnement (.env)

```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_API_VERSION=2024-06-20
```

Côté frontend (`v0-secure-point-dashboard-design/.env.local`) :

```
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...
```

### 3. Migrer la base

```bash
python manage.py migrate billing
```

### 4. Créer les Produits / Prix dans Stripe

Dans le Dashboard Stripe (test mode) :

1. Products → New product → "Plan Pro" → ajouter un Price récurrent (12 €/mois)
2. (Optionnel) Ajouter `metadata.plan_code = pro` au product pour figer le slug
3. Pour la facturation à l'usage : créer un Price de type "Recurring" → "Usage is metered"

Puis synchroniser le catalogue local :

```bash
python manage.py sync_stripe_plans
```

### 5. Configurer le webhook

**En dev** (avec la CLI Stripe) :

```bash
stripe listen --forward-to http://localhost:8000/api/billing/webhook/
```

La commande affiche un `whsec_...` à mettre dans `STRIPE_WEBHOOK_SECRET`.

**En prod** : Dashboard Stripe → Developers → Webhooks → Add endpoint
`https://votre-domaine.com/api/billing/webhook/` et cocher au minimum :

- `checkout.session.completed`
- `customer.subscription.created/updated/deleted`
- `invoice.paid` / `invoice.payment_failed`
- `payment_intent.succeeded` / `payment_intent.payment_failed`

## Endpoints API

Tous sous `/api/billing/`. Authentification JWT requise sauf `/plans/` et
`/webhook/`.

| Méthode | Endpoint                                | Description                                       |
|---------|-----------------------------------------|---------------------------------------------------|
| GET     | `/plans/`                               | Catalogue public des plans actifs                 |
| GET     | `/summary/`                             | Abonnement courant + factures ouvertes du tenant  |
| GET     | `/subscriptions/`                       | Abonnements du tenant                             |
| POST    | `/subscriptions/{id}/cancel/`           | Annule à la fin de la période courante            |
| POST    | `/subscriptions/{id}/resume/`           | Annule l'annulation programmée                    |
| GET     | `/invoices/`                            | Factures du tenant                                |
| GET     | `/payments/`                            | Paiements ponctuels du tenant                     |
| POST    | `/checkout/subscription/`               | Crée une session Checkout (subscription)          |
| POST    | `/checkout/one-time/`                   | Crée une session Checkout (paiement unique)       |
| POST    | `/payment-intent/`                      | Crée un PaymentIntent (Stripe Elements)           |
| POST    | `/portal/`                              | Crée une session Customer Portal                  |
| POST    | `/webhook/`                             | Receveur webhook Stripe (signature vérifiée)      |

### Exemple : démarrer un abonnement

```bash
curl -X POST http://localhost:8000/api/billing/checkout/subscription/ \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"plan_code": "pro"}'
```

Réponse :

```json
{
  "session_id": "cs_test_...",
  "url": "https://checkout.stripe.com/c/pay/cs_test_...",
  "publishable_key": "pk_test_..."
}
```

Rediriger l'utilisateur vers `url` — Stripe gère tout le flow et redirige
ensuite vers `success_url`. Le webhook `customer.subscription.created` mettra
à jour le tenant.

### Exemple : facturer à l'usage

```python
from billing.models import Subscription
from billing.services import report_usage

sub = Subscription.objects.get(tenant=tenant, status="active")
report_usage(
    subscription=sub,
    quantity=42,                  # nombre d'évènements / dispositifs / etc.
    idempotency_key=f"event-{event_id}",  # évite le double-comptage
)
```

## Composants frontend

```tsx
import { StripeCheckoutButton } from "@/components/billing/stripe-checkout-button"
import { StripePortalButton } from "@/components/billing/stripe-portal-button"
import { StripePaymentElement } from "@/components/billing/stripe-payment-element"
import { LiveSubscriptionCard } from "@/components/billing/live-subscription-card"

// Abonnement (Checkout hébergé)
<StripeCheckoutButton mode="subscription" planCode="pro">
  Souscrire à Pro
</StripeCheckoutButton>

// Paiement ponctuel (Checkout hébergé)
<StripeCheckoutButton mode="one_time" amountCents={9900} description="Frais d'installation">
  Payer 99 €
</StripeCheckoutButton>

// Paiement intégré (Payment Element)
<StripePaymentElement
  amountCents={9900}
  description="Frais d'installation"
  onSuccess={(piId) => router.push(`/billing?payment=success`)}
/>

// Portail client Stripe
<StripePortalButton>Gérer mon abonnement</StripePortalButton>

// Récap abonnement live
<LiveSubscriptionCard />
```

La page `/pricing` (`app/pricing/page.tsx`) liste automatiquement tous les
plans actifs et propose le bon CTA selon que l'utilisateur est connecté ou non.

## Tester en local

```bash
# Terminal 1 — backend
python manage.py runserver 0.0.0.0:8000

# Terminal 2 — Stripe webhook tunnel
stripe listen --forward-to http://localhost:8000/api/billing/webhook/

# Terminal 3 — frontend
cd v0-secure-point-dashboard-design && pnpm dev
```

Cartes de test Stripe :

| Numéro                | Comportement       |
|-----------------------|--------------------|
| `4242 4242 4242 4242` | Paiement réussi    |
| `4000 0025 0000 3155` | Demande 3DS        |
| `4000 0000 0000 9995` | Décliné — fonds insuffisants |

CVV : n'importe quel 3 chiffres. Date : n'importe quelle date future.

## Sécurité

- Le `STRIPE_SECRET_KEY` ne doit JAMAIS être exposé côté client. Côté front,
  on utilise uniquement `pk_*` (publishable).
- Le webhook vérifie la signature via `STRIPE_WEBHOOK_SECRET`. En dev sans
  secret, on log un warning et on accepte le payload (utile pour les tests
  manuels mais désactivez ce mode en prod).
- Les opérations de facturation sont restreintes aux membres `tenant_admin`
  via `assert_can_manage_billing` (cf. `permissions.py`).
- Toutes les requêtes sont scopées au tenant courant (résolu via
  `X-Tenant-Code` header ou la membership primaire).

## Essai gratuit & multi-devise

### 1. Modèle Plan — nouveaux champs

| Champ                  | Type    | Rôle                                                                 |
|------------------------|---------|----------------------------------------------------------------------|
| `trial_period_days`    | int     | Durée du trial. `0` = pas de trial. Ex : `14`.                       |
| `trial_requires_card`  | bool    | `False` (défaut) → pas de CB demandée à l'inscription au trial.      |

Migrer la base :

```bash
python manage.py migrate billing
```

### 2. Configurer Stripe Dashboard

Sur chaque **Product** Stripe (ex : "Plan Pro"), ajoutez ces metadata :

```
plan_code               = pro
trial_period_days       = 14
trial_requires_card     = false
device_quota            = 50
event_quota_per_month   = 100000
has_priority_support    = true
has_advanced_analytics  = true
```

Pour le **multi-devise**, créez **un Price par devise** sur le même Product
(ex : 29 EUR, 32 USD, 19000 XOF). La page `/pricing` filtre les Plans par
devise via `?currency=eur`.

Puis re-synchronisez le catalogue local :

```bash
python manage.py sync_stripe_plans
```

### 3. Démarrer un trial sans CB depuis le frontend

La page `/pricing` détecte automatiquement les plans avec
`trial_period_days > 0 && !trial_requires_card` et affiche un bandeau
**« Essai 14 jours · Sans CB »**. Le bouton appelle
`POST /api/billing/checkout/subscription/` qui crée la session Checkout avec :

- `payment_method_collection: "if_required"` — Stripe n'exige pas la CB.
- `subscription_data.trial_period_days: 14`
- `subscription_data.trial_settings.end_behavior.missing_payment_method: "cancel"` — si le client n'a pas ajouté de CB à J+14, l'abonnement est annulé proprement plutôt que de passer en `past_due`.

### 4. Sélecteur de devise

`GET /api/billing/plans/currencies/` → liste des devises disponibles
(`["eur","usd","xof"]`).
`GET /api/billing/plans/?currency=eur` → plans filtrés.
La page `PricingPageClient` mémorise le choix dans `localStorage`.

### 5. Stripe Tax (TVA automatique, optionnel)

Activez la TVA auto sur Checkout :

```env
STRIPE_AUTOMATIC_TAX=true
```

Et dans le Stripe Dashboard → Settings → Tax → activer Stripe Tax pour vos
juridictions.

### 6. Smoke test rapide

```bash
# 1) backend
python manage.py migrate billing
python manage.py sync_stripe_plans
python manage.py runserver 8000

# 2) webhook (autre terminal)
stripe listen --forward-to http://localhost:8000/api/billing/webhook/

# 3) frontend
cd v0-secure-point-dashboard-design
pnpm dev
# Ouvrir http://localhost:3000/pricing
```

Cliquer sur "Démarrer l'essai gratuit" → Stripe Checkout doit s'ouvrir
**sans champ carte bancaire**. Compléter avec un email → retour sur
`/billing?checkout=success`.

## Mur d'upgrade (paywall)

Le frontend dispose d'un système de gating en 4 pièces, alimenté par le hook
`useTenantPlan` qui consomme `/api/billing/summary/` :

| Pièce               | Fichier                                              | Rôle                                                                        |
|---------------------|------------------------------------------------------|-----------------------------------------------------------------------------|
| `useTenantPlan`     | `hooks/use-tenant-plan.ts`                           | Hook qui expose `plan`, `tier`, `hasFeature(key)` à toute l'app             |
| `<FeatureGate>`     | `components/billing/feature-gate.tsx`                | Cache un sous-arbre derrière le mur d'upgrade                                |
| `<UpgradeWall>`     | `components/billing/upgrade-wall.tsx`                | Le mur d'upgrade lui-même (plein contenu ou compact)                         |
| `<UpgradeDialog>`   | `components/billing/upgrade-dialog.tsx`              | Modal d'upgrade ouvert depuis un CTA                                         |
| `<ProBadge>`        | `components/billing/pro-badge.tsx`                   | Petit tag "Pro" / "Enterprise" à côté d'un libellé                           |

### 1. Définir les features

Pour chaque Plan, ajoutez les flags dans le champ `features` (JSON) côté
admin Django :

```json
{
  "api_access": true,
  "advanced_analytics": true,
  "multi_site": true,
  "webhooks": true,
  "white_label": false,
  "sso": false,
  "retention_days": 365
}
```

Ou bien via les metadata du Product dans Stripe Dashboard, en préfixant chaque
feature par `feat.` :

```
feat.api_access         = true
feat.advanced_analytics = true
feat.retention_days     = 365
```

`python manage.py sync_stripe_plans` les recopie automatiquement dans le champ
`features` du Plan local.

Le catalogue des feature keys connues du frontend est dans
[`lib/billing/feature-access.ts`](../../v0-secure-point-dashboard-design/lib/billing/feature-access.ts)
(constante `FEATURE_META`). Ajoutez-y une nouvelle entrée pour qu'`UpgradeWall`
sache afficher un titre joli.

### 2. Gater un sous-arbre — `<FeatureGate>`

```tsx
import { FeatureGate } from "@/components/billing/feature-gate"

// Mode "replace" (défaut) : remplace le contenu par <UpgradeWall>
<FeatureGate feature="api_access">
  <ApiKeysPanel />
</FeatureGate>

// Mode "preview" : empile le mur par-dessus un aperçu flou
<FeatureGate feature="advanced_analytics" mode="preview">
  <BigChart />
</FeatureGate>

// Mode "hide" : ne rend rien (parfait pour des items de menu)
<FeatureGate feature="sso" mode="hide">
  <SidebarItem href="/settings/sso" label="SSO / SAML" />
</FeatureGate>

// Gating par tier au lieu d'une feature précise :
<FeatureGate requiredTier="enterprise">
  <WhiteLabelSettings />
</FeatureGate>
```

### 3. Gater un bouton — `<UpgradeDialog>`

```tsx
import { useState } from "react"
import { UpgradeDialog } from "@/components/billing/upgrade-dialog"
import { useTenantPlan } from "@/hooks/use-tenant-plan"

function GenerateApiKeyButton() {
  const { hasFeature } = useTenantPlan()
  const [openUpgrade, setOpenUpgrade] = useState(false)

  if (!hasFeature("api_access")) {
    return (
      <>
        <Button onClick={() => setOpenUpgrade(true)}>
          Générer une API key
        </Button>
        <UpgradeDialog
          open={openUpgrade}
          onOpenChange={setOpenUpgrade}
          feature="api_access"
        />
      </>
    )
  }
  return <Button onClick={createApiKey}>Générer une API key</Button>
}
```

### 4. Étiqueter une feature — `<ProBadge>`

```tsx
import { ProBadge } from "@/components/billing/pro-badge"

<h3>Webhooks <ProBadge tier="pro" /></h3>
<h3>SSO <ProBadge tier="enterprise" /></h3>
```

### 5. Logique custom — `useTenantPlan()`

```tsx
import { useTenantPlan } from "@/hooks/use-tenant-plan"

function MyComponent() {
  const { tier, hasFeature, hasActiveSubscription, refresh } = useTenantPlan()

  if (tier === "free" && !hasActiveSubscription) {
    return <FreeTeaserBanner />
  }
  // ...
}
```

Le hook se rafraîchit automatiquement quand l'onglet reprend le focus (utile
au retour de Stripe Checkout). Pour forcer manuellement : `refresh()`.

### 6. Ajouter une nouvelle feature gated — checklist

1. Ajouter une entrée dans `FEATURE_META` (`lib/billing/feature-access.ts`)
   avec `title`, `description`, et `minPlan`.
2. Décider : flag explicite (`feat.ma_feature = true` dans Stripe) ou
   inférence par tier ? Pour les features critiques, préférez le flag explicite.
3. Wrapper le composant cible dans `<FeatureGate feature="ma_feature">`.
4. Si la feature a un coût serveur (export PDF, appel API externe), gater
   AUSSI côté backend dans la vue DRF — le frontend gating ne suffit pas
   pour la sécurité.
