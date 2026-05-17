# LR Time — Operator Dashboard UI Kit

This kit contains the production operator console for LR Time: the screens HR directors, security supervisors, and site managers use every morning.

## Screens included

- **Login** — bilingual (FR), tenant-aware, with the "demo mode" affordance.
- **Dashboard (Tableau de bord)** — morning diagnostic: 4 KPI tiles, live presence chart, anomalies queue, device status strip.
- **Devices (Appareils)** — Hikvision device inventory with live status, firmware, IP, and a side drawer for one-device focus.
- **Employees (Employés)** — directory with biometric enrolment status and per-row actions.

## How to view

Open `index.html` in a browser. A small navigation chrome at the top lets you jump between screens. Hover any device row, click "Configurer" to open the side drawer.

## Implementation notes

- Built in React 18 + Babel inline transpile (no build step).
- Components live in their own `*.jsx` files and are exported to `window` so other scripts can import them.
- All styles come from CSS variables defined in `../../colors_and_type.css`.
- Icons use the symbol bank in `../../assets/icons.svg` via `<use href>`.
- Avatars are initialed circles with the brand peach→orange gradient. No photographic avatars.

## Why these screens

The Next.js source codebase has 30+ routes (devices, employees, planning, reports, billing, surveillance, audit, alerts, profile, settings, biometric-enrollment, anomalies, …). For this UI kit we picked the **four screens an operator hits in their first 90 seconds** of the day:

1. **Login** — they need to get in.
2. **Dashboard** — the morning glance.
3. **Devices** — when something on the dashboard is red.
4. **Employees** — when they need to act on a person.

The other screens (Planning, Reports, Billing, Surveillance) reuse the exact same components and patterns shown here.
