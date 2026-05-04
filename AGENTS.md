# AGENTS

## Project Map (Fast Entry)
- Backend (Django): `C:\Users\PC MARKET\Downloads\hikvision-django-integration\app`
- Frontend (Next.js): `C:\Users\PC MARKET\Downloads\hikvision-django-integration\v0-secure-point-dashboard-design` (submodule)
- Backlog de commercialisation : voir `BACKLOG.md` à la racine.

## Where To Work
- Backend code and API changes: work only inside `app/`
- Frontend UI and client changes: work only inside `v0-secure-point-dashboard-design/`
- Root folder contains infra/docs only (`docker-compose.yml`, top-level `README.md`, PDFs, logs)

## Quick Start Commands
- Backend:
  - `cd app`
  - `python manage.py runserver`
- Frontend:
  - `cd v0-secure-point-dashboard-design`
  - `npm run dev`

## Agent Rule
Do not scan the whole repository first. Start from this map and enter only the relevant workspace (`app/` for backend, `v0-secure-point-dashboard-design/` for frontend).

---

## Sprint Workflow (commercialisation)

Le projet est piloté par sprints courts (2–4 h d'effort modèle) listés dans `BACKLOG.md`. Toute session de codage doit respecter les règles ci-dessous.

### Avant de commencer un sprint
1. Lire l'entrée du sprint dans `BACKLOG.md` (objectif, livrable, critères de validation).
2. Si le scope semble dépasser 4 h, **proposer un split** avant d'écrire du code.
3. Ne jamais démarrer un sprint dont la case précédente n'est pas cochée comme validée par l'humain.

### Pendant le sprint
- Un sprint = un livrable focalisé. Pas de refactor opportuniste, pas de cleanup hors scope.
- Pas de nouvelles dépendances sans le mentionner explicitement dans le résumé final.
- Si un blocage apparaît (config manquante, ambiguïté métier), s'arrêter et demander.

### Definition of Done (obligatoire pour clôturer un sprint)
- [ ] Code écrit, lints OK (`ruff check app/`, `black --check app/` une fois ces outils installés ; sinon noter l'absence).
- [ ] Tests unitaires nouveaux ajoutés couvrant le livrable.
- [ ] **Suite complète passe** : `cd app && python manage.py test` (ou `pytest`) — log final attaché au résumé.
- [ ] Migrations générées et appliquées sur DB vide sans erreur.
- [ ] Mini-checklist manuelle décrite (curl/Postman, étapes UI, etc.).
- [ ] Diff résumé en fin de sprint avec : fichiers touchés, risques, points à valider humainement.
- [ ] Backlog mis à jour : la case du sprint est marquée `[~]` (en attente validation), JAMAIS `[x]` directement — seul l'humain coche `[x]`.

### Interdits
- `git commit --no-verify`, `git commit --amend` sur un commit poussé, `git push --force` sur `main`.
- Modifier `settings.py`, `docker-compose.yml`, `.env*`, `requirements.txt`, `package.json` sans le déclarer en tête de résumé.
- Stocker un secret en clair dans le repo. Toujours via env-var + `.env.example`.
- Toucher au schéma BDD sans migration explicite.
- Cocher `[x]` une case du backlog : c'est l'humain qui valide.

### Validation humaine
À la fin de chaque sprint, l'humain :
1. Relit le diff.
2. Lance la checklist manuelle.
3. Coche `[x]` la case dans `BACKLOG.md` ET signe avec `— validé YYYY-MM-DD`.
4. Donne le feu vert pour le sprint suivant.

Tant que ce signal n'est pas donné, ne pas démarrer le sprint suivant.
