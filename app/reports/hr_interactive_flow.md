# Guide d'utilisation - Flux interactif RH

Ce guide decrit comment exploiter le flux `app/reports/hr_interactive_flow.json` pour attribuer des quarts de travail avec logique RH (semaine/week-end, rotation, exceptions, pointage).

## 1. Objectif

Le flux couvre:

- quarts simples ou multiples
- horaires differents en week-end
- planning fixe ou tournant
- exceptions temporaires
- regles RH (retard, sortie, heures sup)
- affectation a des employes ou des departements

## 2. Fichier principal

- Configuration du wizard: `app/reports/hr_interactive_flow.json`

Le JSON contient:

- les questions a poser (ordre, types, conditions)
- les regles de validation metier
- le plan d'appels API pour creation et affectation
- les verifications finales cote planning et reporting

## 3. Scenario recommande (ton cas)

Si les employes travaillent le week-end avec des horaires differents:

1. Creer au moins 2 quarts:
- `SEMAINE_JOUR` (ex: `08:00-17:00`)
- `WEEKEND_JOUR` (ex: `09:00-14:00`)

2. Choisir `planning_style = fixed`

3. Mapper les jours:
- `day_of_week 0..4` -> `SEMAINE_JOUR`
- `day_of_week 5..6` -> `WEEKEND_JOUR`

4. Activer les regles RH utiles:
- `late_allowable_minutes`
- `early_leave_allowable_minutes`
- `effective_for_overtime`
- `flexible_weekend` si necessaire

5. Appliquer aux cibles:
- employes (`/api/employees/{id}/assign-planning/`)
- ou departements (`/api/departments/{id}/assign-planning/`)

## 4. Execution API (ordre)

1. `POST /api/work-shifts/` (creation quarts)
2. `POST /api/plannings/` (creation planning + entries)
3. assignation planning aux cibles
4. `POST /api/planning-assignments/` (regles RH avancees: validite, overtime, weekend flexible, priorite)

Le detail des payloads templates est deja dans `api_execution_plan` du JSON.

## 5. Verification apres application

1. Verifier le rendu mensuel:
- `GET /api/employees/{id}/schedule/?month=YYYY-MM`

2. Verifier la conformite RH:
- `GET /api/hikgateway/reports/attendance/?period=weekly&tenant={tenant_code}`

## 6. Notes d'integration frontend

- Le flux peut etre charge comme schema declaratif pour un wizard dynamique.
- Chaque `step` du JSON peut etre rendu en composant UI selon `type`.
- Les champs `show_if` pilotent l'affichage conditionnel.
- Les blocs `rules` servent aux validations avant l'appel API.
