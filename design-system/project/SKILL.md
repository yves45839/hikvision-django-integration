---
name: lr-time-design-system
description: Design system for LR Time, a French SaaS for time & attendance + access control plugged into Hikvision biometric readers and cameras. Use when designing operator-facing screens (HR director, security supervisor, site manager): morning diagnostic dashboards, device inventories, employee directories, planning, reports, alerts, audit. The visual identity is "Stripe / Notion light corporate" — deep institutional blue with a warm orange accent, slate neutrals, Inter Tight display + Inter body + JetBrains Mono for technical strings (IPs, firmware, timestamps). French-first copy, sentence case, no emoji, status conveyed by colored dots and badges. Apply this skill when the user mentions "LR Time", "Hikvision dashboard", "pointage / présence / appareil / lecteur" UI work, or asks for screens that look like the existing operator console.
---

# LR Time — Design System

You are designing for **LR Time**, the operator console of a Hikvision-integrated time & attendance and access control SaaS. Read `README.md` first — it is the source of truth for the visual language, copy voice, and component anatomy.

## Where things live

```
README.md                    Full design system documentation
colors_and_type.css          Canonical CSS variables (tokens) — always link this
assets/
  lr-logo.svg                Logo mark (gradient, white "L" glyph)
  lr-wordmark.svg            Logo + "LR Time" wordmark
  icons.svg                  Lucide-style symbol bank — use via <use href="…icons.svg#i-name">
  source-tokens.css          Original tokens.css from refonte (verbatim, for reference)
preview/                     One review card per token / component
  colors-*.html              Brand, neutral, status, semantic palettes
  type-*.html                Scale + families
  spacing-grid.html · radii.html · shadows.html · motion.html
  buttons.html · badges.html · inputs.html · card.html · kpi.html
  table-row.html · sidebar-item.html · topbar.html · empty-state.html
  logo.html · icons.html
ui_kits/
  operator-dashboard/        Production operator console reference
    index.html               Click-thru: Login → Dashboard → Devices → Employees
    Sidebar.jsx · Topbar.jsx · KpiCard.jsx
    LoginScreen.jsx · DashboardScreen.jsx · DevicesScreen.jsx · EmployeesScreen.jsx
    styles.css               Shared chrome (imports colors_and_type.css)
```

## Quick rules to internalise

- **Tokens, never hex.** `var(--brand)`, `var(--fg1)`, `var(--shadow-sm)` — not `#2F6BE6`. The token file is your contract.
- **Type:** Inter Tight 600 for display + KPI numbers, Inter 400/500/600 for body, JetBrains Mono 500 for IPs / firmware / timestamps / IDs. Letter-spacing tight on display (`-0.015em` to `-0.025em`), wide on eyebrows (`.08em` uppercase).
- **Spacing:** strict 4-pt grid. Page gutter 32 px desktop.
- **Cards:** white surface, 1 px `--border-default`, 16 px radius, `--shadow-sm`. Header 20/20/12 padding, body 12/20/20. **Never** add a colored top-strip or left-border accent to a card — that's an anti-pattern in this system.
- **Buttons:** 38 px tall, 8 px radius, sentence case ("Ajouter un appareil", never "Add Device"). Primary = brand blue, hover darkens one step, active translateY(1px).
- **Badges:** 22 px pill, colored dot + label. Live status uses an animated green pulse (1.6 s, infinite).
- **Sidebar active item:** brand-soft background + brand-active text + 3-px solid left accent. No outlines.
- **Tables:** 7 columns max visible; rest in a side drawer. Selected row gets a 3-px brand left accent. Headers UPPERCASE 11 px, .08 em letter-spacing.
- **Animation:** three durations — 120 ms / 200 ms / 320 ms. Curves: `ease-out` for entry, `ease-in-out` for both-direction. **No bounces, no springs.** Only one looping animation: the live-status green pulse.
- **Focus:** ring-based, never border-color-based. `box-shadow: var(--shadow-focus)`.
- **Topbar:** sticky 60 px, white at 85% with `saturate(140%) blur(8px)` backdrop. The only blur in the body chrome.

## Copy voice (don't skip this)

- **French primary.** "Vous" form, never tutoiement. Action verbs lead labels: *Valider, Réenrôler, Examiner, Corriger*.
- **Sentence case** for everything (titles, buttons, menu items). ALL CAPS only for eyebrows and table column headers.
- **Numbers carry context.** Never *"142 présents"* alone — say *"142 présents sur 163 attendus · 87% de couverture"*.
- **No emoji.** Status is dots + badges + pulses. Don't reach for 🟢 🟠 🔴.
- **Empty states teach the next action**, with a single primary CTA. *"Aucun appareil détecté. Connectez votre première caméra Hikvision pour démarrer la supervision."*
- **Errors are honest and kind.** *"Impossible de joindre HikCentral — réessai dans 12 s"* — never raw stack traces.

## Iconography

Source of truth is **lucide-react** (the production app uses it). In HTML mockups, use the symbol bank at `assets/icons.svg`:

```html
<svg width="16" height="16"><use href="../../assets/icons.svg#i-cpu" /></svg>
```

1.6 px stroke, rounded line-caps and joins, currentColor only. Never re-color icons with hard hex — they inherit from the parent.

## Imagery

When product imagery is needed (Hikvision device thumbnails, biometric reader shots), use **clean white-background product shots** — no vignettes, no grain, neutral cool-warm balance. Avatars are initialed circles with a peach-200 → orange-500 135° gradient. **No photographic avatars by default.** No hand-drawn illustrations, no abstract textures.

## Starting a new screen

1. Link `colors_and_type.css` (and, for app-shell screens, `ui_kits/operator-dashboard/styles.css`).
2. Reuse `Sidebar`, `Topbar`, `KpiCard`, `.card`, `.btn`, `.badge`, `.tbl`, `.drawer` — they cover ~90% of operator surfaces.
3. Pick 1–2 KPIs that matter for the morning glance, anchor every number with its denominator and delta.
4. Live data → tiny green `Live` pill + last-refresh timestamp in mono muted text.
5. If the data is empty, write an empty state that names the next action.
6. No section adds visual weight (gradient, color block, illustration) unless it's load-bearing. Default to the calm cockpit.

## What this system is not

- Not a marketing site kit — no big hero gradients, no oversized type, no testimonial blocks.
- Not a data-viz library — keep charts to sparklines, simple bars, single-series lines. The point is the decision, not the visualisation.
- Not consumer-grade — no playful microcopy, no bouncy animations, no emoji. The user is a manager triaging a morning of clocking events.
