# LR Time — Design System

LR Time is a French SaaS for **time & attendance and access control**, plugged into the **Hikvision** ecosystem (biometric readers, turnstiles, cameras). Target users: HR directors, security supervisors, site managers, planning managers — they come for a fast morning diagnostic, clear decisions, and irreproachable payroll exports.

The product line, as observed in the source codebase, is bilingual (FR primary, EN secondary) and currently spans:

- A **Django/DRF backend** (`hikvision-django-integration/app/`) handling auth (JWT), multi-tenant, devices, employees, plannings, events, attendance reports, and the Hik Device Gateway integration.
- A **Next.js dashboard** (`hikvision-django-integration/v0-secure-point-dashboard-design/`) — the operator-facing web app: dashboard, devices, employees, planning, reports, billing, surveillance, audit, etc.
- A **refonte (UX/UI redesign brief)** — `hikvision-django-integration/design-refonte-lr-time/` — five static HTML mockups + a published design-tokens file describing the target "light corporate" direction (Stripe / Notion family).

This design system is the operator-facing visual identity: deep-blue institutional, warm-orange accent, slate neutrals, Inter Tight for display, Inter for body, JetBrains Mono for technical strings (IPs, firmware, timestamps, IDs).

---

## Sources

| Source | Path | Notes |
| --- | --- | --- |
| Backend codebase | `hikvision-django-integration/app/` | Django models, REST endpoints, business logic |
| Dashboard codebase (Next.js) | `hikvision-django-integration/v0-secure-point-dashboard-design/` | Tailwind v4 + shadcn/ui, OKLCH tokens in `app/globals.css` |
| Refonte brief | `hikvision-django-integration/design-refonte-lr-time/brief.html` | Personas, audit, principles, roadmap |
| Refonte mockups | `hikvision-django-integration/design-refonte-lr-time/pages/*.html` | Dashboard, Devices, Employees, Reports, Planning |
| Refonte tokens (canonical) | `hikvision-django-integration/design-refonte-lr-time/tokens.css` | Where this system's CSS variables come from — copied to `assets/source-tokens.css` |

> Reader note: these paths are read-only and may not be present in the published design system folder. The salient values were extracted into `colors_and_type.css` and the cards in `preview/`.

---

## Content fundamentals

LR Time copy is **French-first, professional but warm**, tuned for HR/security decision-makers who want to scan a screen and act in seconds.

**Tone & voice**
- Calm, factual, slightly directive. Sentences short. "Diagnose, decide, export."
- "Vous" form (formal *you*), never tutoiement. Action verbs lead labels: *Valider, Réenrôler, Examiner, Corriger*.
- Numbers are anchored in context: never a metric without its denominator or its delta. *"142 employés présents sur 163 attendus — objectif hebdo 90%"* not just *"142 présents"*.
- Empty states **teach the next action**, with a single primary CTA. *"Connectez votre première caméra Hikvision pour démarrer la supervision."*
- Errors are honest and kindly worded: *"Impossible de joindre HikCentral — réessai dans 12 s"* — never raw stack traces.

**Casing**
- Sentence case for buttons, titles, menu items: *Tableau de bord*, *Ajouter un appareil*. Never Title Case.
- ALL CAPS reserved for **eyebrows** (section overlines) and **table column headers**, with `.08em` letter-spacing.

**Vocabulary (FR canonical)**
- *Présence* (presence), *pointage* (clock-in event), *appareil* (device), *lecteur* (reader), *quart* (shift), *anomalie* (clocking anomaly), *biométrie* (biometric enrolment), *gateway* / *passerelle*, *tenant*, *organisation*, *site*.
- Avoid corporate jargon ("synergize", "leverage"). Avoid English when a clean French exists, except for product-API names (HikCentral, gateway).

**Emoji**: not used. Status is communicated by **colored dots, badges, and pulse animations**, not by 🟢 / 🟠 / 🔴.

**Vibe**: trustworthy SaaS. The product replaces panicked Excel sheets and unreadable Hikvision admin panels — it should feel like a clean cockpit, never an arcade.

**Examples (lifted from the codebase)**
- Hero subtitle: *"142 personnes pointées · 87% de couverture · 5 anomalies à traiter avant 11 h"*
- KPI label: *Présents aujourd'hui* / *Appareils actifs* / *Retards* / *Absences*
- Empty state: *"Aucun employé importé. Connectez votre annuaire ou importez un CSV."*
- Toast: *"Nadia déplacée vers RH. Annuler."*
- Sidebar footer: *"Gateway connectée · tenant: ACME-CASA"*

---

## Visual foundations

**Palette philosophy.** A **deep institutional blue** (`#2F6BE6` brand 500, deepening to `#173FA1` on press) signals trust and software gravity. A **warm orange** (`#F97316`) is reserved for *energy* moments — alerts asking for human action, the user's avatar gradient, the topbar bell dot, the demo-mode banner. The neutral spine is **slate** — slightly cool, never pure gray, with a faint warm bias around `#FBFCFD` to keep large surfaces from looking sterile.

**Type.** Display = **Inter Tight 600** (subtly more compressed than Inter; gives KPI numbers and section titles a "premium dashboard" feel). Body = **Inter 400/500/600**. Technical = **JetBrains Mono 500** for IP addresses, firmware versions, timestamps, IDs. Letter-spacing is tight on display (`-0.015em` to `-0.025em`), wide on eyebrows/table headers (`.08em` uppercase).

**Spacing.** Strict **4-pt grid** (4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64 / 96). Page gutter 32 px desktop, 16 px tablet. No arbitrary inline margins.

**Backgrounds.** Mostly flat slate-50 (`#F7F9FC`). Hero/CTA cards use a **diagonal blue gradient** `linear-gradient(135deg, #2F6BE6 → #112E78)` with a white-radial highlight in the corner. No photography baked into the system; product imagery (device photos, biometric reader shots) is brought in per-page when needed. **No** repeating patterns, **no** hand-drawn illustrations, **no** abstract textures. The only "soft grid" is a subtle 28px dot-grid on the dashboard shell, opacity ≈ 0.022.

**Animation.** Three durations only: **120 ms** (button press / focus ring), **200 ms** (default — hover, color change, card lift), **320 ms** (page-level transitions). Curves: `ease-out` (cubic-bezier(.2,.7,.2,1)) for entry, `ease-in-out` for both-direction transitions. **No bounces, no springs.** The one repeating animation is the **green pulse** on live status (1.6 s, ease-out, infinite) — used sparingly: gateway-connected indicator, "actif il y a 12 s" device dot.

**Hover states.** Buttons → background darkens by one step (e.g., `--brand-500` → `--brand-600`). Card hover → 1 px translateY(-1px) + shadow upgrade (`--shadow-sm` → `--shadow-md`) + border softens to `--lr-blue-200`. Sidebar item → `--slate-50` background, icon color shifts to `--fg2`. **Never** opacity-only hovers — they look broken.

**Press states.** Buttons → background goes one step darker (`--brand-700`), no shrink. Sidebar items → background `--brand-soft`, left 3-px accent appears.

**Focus.** Ring-based, never border-color-based. `box-shadow: 0 0 0 3px rgba(47,107,230,.18)`. Danger variant uses red equivalent. Outline never visible — `outline: none` only with the ring shadow.

**Borders.** 1 px `--border-default` (#E4E9F1) is the workhorse. `--border-subtle` (#EFF2F7) for table row separators. `--border-strong` (#D6DEE9) for hovered/secondary buttons. **No 2 px borders anywhere.** Active sidebar items use a **3-px solid left accent** (brand) plus a soft brand-tint background.

**Shadows / elevation.** Five steps, all **double-layer Stripe-style** (one large diffuse + one tight definition). Cards use `--shadow-sm`. Hovered cards `--shadow-md`. Drawers/modals `--shadow-xl`. Inset shadows reserved for inputs and "puits" (e.g., dashboard input-bg). KPI tiles get an additional inner-bottom hairline (`inset 0 -1px 0`) to look pressed-in.

**Protection gradients vs capsules.** Pills/capsules win — `border-radius: 999px` for status badges, filter chips, count pills. Gradients are **never** used to protect text against imagery (no glassy strips). The only colored gradients live on: the brand logo mark (135° blue 500→700), CTA hero cards (135° blue 500→800), and the user avatar (135° peach-200 → orange-500). Linear gradients are **always 135°**.

**Layout rules.**
- Two-column shell: 248 px sidebar (sticky, full height) + flexible content. Topbar 60 px sticky with backdrop blur (`saturate(140%) blur(8px)`) at 85% white opacity.
- Content max-width 1440 px, page padding 32 px desktop / 24 px tablet / 16 px mobile.
- **Tables breathe**: 7 columns max visible by default, the rest in a side drawer. Selected row gets a 3-px brand accent on the left.
- Sidebar groups labels are uppercased eyebrows. Active item: `--brand-soft` background, `--brand-active` text.

**Transparency / blur.** Used in exactly two places: the topbar (white 85% + saturate/blur) and modal/drawer overlays (slate-900 at 40% with no blur). **No glass cards** in the body, **no frosted side panels**.

**Imagery vibe.** When product photography is brought in (Hikvision device thumbnails, biometric reader shots), it's **clean white-background product shots, neutral cool-warm balance**, no vignettes, no grain. Avatars are initialed circles with a **peach-200 → orange-500 gradient** at 135°. No photographic avatars by default.

**Corner radii.** `4 / 6 / 8 / 12 / 16 / 20 / 28 px` + `pill (999)`. Buttons 8 px (sm 6 px, lg 12 px). Inputs 8 px. Badges 12 px or pill. **Cards 16 px** (this is the canonical "card radius"). Hero / KPI tiles 16 px. CTA banners 20 px. Modal/drawer 16 px. **Rule of nesting**: outer is always rounder than inner.

**Cards anatomy.** White surface (`--bg-surface`), 1 px `--border-default`, `--radius-xl` (16 px), `--shadow-sm`. Header padding 20px / 20px / 12px, body 12px / 20px / 20px. Header has title (display, 14.5 px, 600), optional subtitle (muted, 12.5 px), and right-aligned actions. No colored top-strips, no left-border accents (anti-pattern in this system).

**Live / data freshness.** Tiny green pill `Live` (with pulse) sits in the corner of any live data card. Stale data shows a `t-mono` timestamp ("il y a 12 s") in muted text — never a spinner once initial load is done.

---

## Iconography

**Source of truth: `lucide-react`.** The Next.js codebase uses Lucide consistently — `LayoutDashboard, Users, Cpu, BarChart3, Shield, CalendarDays, Settings, Bell, Search, Plus, ChevronDown, ArrowUpRight, Clock, UserX, AlertTriangle, CheckCircle2, XCircle, MoreHorizontal, Eye, Zap, Target` etc. Stroke-based, 1.6 px stroke (`stroke-width="1.6"`), rounded line-caps and joins. Icons are **monochrome currentColor** — color comes from the parent's `color` property.

**Standard sizes.** 13 px (inside small buttons), 16 px (sidebar, default in lines of text), 18 px (KPI card top-right), 20 px (hero stats, big CTAs), 36 px wrapper (`kpi__icon`, brand-soft squircle, 8 px radius).

**Asset format.**
- **In HTML mockups (this system):** an inline `<svg width="0" height="0">` symbol bank, used via `<svg><use href="#i-foo"/></svg>`. Stored in `assets/icons.svg` for reuse.
- **In the React app:** import directly from `lucide-react`. No PNG icons.

**Logo / brand mark.** A 32–38 px squircle (radius 8–10 px), 135° blue 500→700 gradient, white "L" glyph (custom `<path>` — see `assets/lr-logo.svg`). On dark surfaces, the gradient stays the same; the glyph remains white. **Never** outline the logo.

**Emoji**: not used. Unicode characters not used as icons (no ✓ ✗ ⚠ — those are Lucide).

**Status dots.** 6–7 px circles, currentColor. Live status uses an 7 px green circle with `box-shadow` pulse animation (see `--shadow-focus` style halo, but in success-500 at 35% opacity).

**Iconography substitutions.** No substitutions made — the Next.js codebase is on Lucide and we kept it.

---

## Index — what's in this folder

```
.
├── README.md                — this file
├── SKILL.md                 — Claude Code-compatible skill manifest
├── colors_and_type.css      — CSS vars + type primitives (the canonical palette)
│
├── assets/
│   ├── lr-logo.svg          — LR Time logo mark (gradient, white glyph)
│   ├── lr-wordmark.svg      — Logo + "LR Time" wordmark + eyebrow
│   ├── icons.svg            — symbol bank (Lucide-style, used by mockups)
│   └── source-tokens.css    — original tokens.css from refonte (verbatim)
│
├── preview/                 — design-system review cards
│   ├── colors-brand.html
│   ├── colors-neutral.html
│   ├── colors-status.html
│   ├── colors-semantic.html
│   ├── type-scale.html
│   ├── type-families.html
│   ├── spacing-grid.html
│   ├── radii.html
│   ├── shadows.html
│   ├── motion.html
│   ├── buttons.html
│   ├── badges.html
│   ├── inputs.html
│   ├── card.html
│   ├── kpi.html
│   ├── table-row.html
│   ├── sidebar-item.html
│   ├── topbar.html
│   ├── empty-state.html
│   ├── logo.html
│   └── icons.html
│
└── ui_kits/
    └── operator-dashboard/  — the LR Time Next.js operator app
        ├── README.md
        ├── index.html       — interactive click-thru (login → dashboard → devices → drawer)
        ├── Sidebar.jsx
        ├── Topbar.jsx
        ├── KpiCard.jsx
        ├── DashboardScreen.jsx
        ├── DevicesScreen.jsx
        ├── EmployeesScreen.jsx
        └── LoginScreen.jsx
```

No slide template was provided, so no `slides/` folder is generated.

---

## How to use this system

Either link `colors_and_type.css` and consume the CSS variables directly, or — when working in the LR Time codebase — the existing `tokens.css` and `app/globals.css` already expose the same variables (with OKLCH equivalents in the latter). Always prefer CSS variables; never hard-code hex values.
