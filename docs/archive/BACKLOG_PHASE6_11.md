# Backlog — Phases 6 et 11 IMPLEMENTATION

## PHASE 6 — Conformité RGPD

### 6.1 — Pages légales
- [x] Créer `app/config/legal_views.py` avec vues TOS + Privacy Policy
- [x] Ajouter routes `/legal/tos/` et `/legal/privacy/` dans `config/urls.py`
- [x] Contenu conforme RGPD (droits art. 15-21, rétention, etc.)

### 6.2 — Export données (Article 20)
- [x] Créer `app/tenants/gdpr_views.py` avec `UserDataExportView`
- [x] Endpoint `GET /api/auth/me/export/` retourne ZIP avec JSON + CSV
- [x] Inclure tous les memberships (tenant + organisation)
- [x] Métadonnées d'export (date, version)

### 6.3 — Effacement (Article 17 - Droit à l'oubli)
- [x] Implémenter `UserDeleteView` pour anonymisation
- [x] Endpoint `DELETE /api/auth/me/` avec confirmation explicite (confirm=true)
- [x] Anonymiser sans supprimer (garder historique pour audit)
- [x] Marquer tokens de vérification comme utilisés

### 6.4 — Consent Log
- [x] Créer modèle `ConsentLog` dans `tenants/models.py`
- [x] Migration 0002_add_consentlog.py

### 6.5 — Rétention configurable
- [x] Créer commande `purge_old_events.py`
- [x] Arguments: `--days` (défaut 90), `--dry-run`, `--event-type`

### 6.6 — Chiffrement biométrie
- [x] Créer `app/employees/biometric_encryption.py`
- [x] Fonctions `encrypt_biometric()` et `decrypt_biometric()` (Fernet)

### 6.7 — DPA téléchargeable
- [x] Créer `app/tenants/dpa_views.py` avec `DPADownloadView`
- [x] Endpoint `GET /api/auth/dpa/` retourne fichier texte complet

---

## PHASE 11 — Résilience Hikvision

### 11.1 — Retry + Circuit Breaker
- [x] Ajouter `tenacity>=8.2` et `pybreaker>=1.0` dans requirements.txt
- [x] Créer `app/hik_gateway/resilience.py`
- [x] Fonction `get_circuit_breaker(tenant_code)`
- [x] Fonction `resilient_gateway_call(func, tenant_code, *args, **kwargs)`

### 11.2 — Health monitoring devices
- [x] Créer commande `hik_health_check_all.py`
- [x] Vérifier disponibilité de chaque device
- [x] Mettre à jour Device.status + offline_hint + last_seen_at

### 11.3 — Déduplication events robuste
- [x] Ajouter index sur `RawEvent.dedupe_key`
- [x] Contrainte UNIQUE sur `dedupe_key`
- [x] Documentation pour `get_or_create()` usage

---

## Fichiers créés

1. `app/config/legal_views.py` — Pages légales TOS + Privacy Policy
2. `app/tenants/gdpr_views.py` — Export + Delete (RGPD)
3. `app/tenants/dpa_views.py` — DPA téléchargeable
4. `app/employees/biometric_encryption.py` — Chiffrement biométrie
5. `app/hik_gateway/resilience.py` — Circuit breaker + Retry
6. `app/hik_gateway/management/commands/purge_old_events.py` — Purge des events
7. `app/hik_gateway/management/commands/hik_health_check_all.py` — Health check
8. `app/tests/test_phase6_rgpd.py` — Tests RGPD
9. `app/tests/test_phase11_resilience.py` — Tests Résilience
10. `app/tenants/migrations/0002_add_consentlog.py` — Migration ConsentLog

## Fichiers modifiés

1. `requirements.txt` — +tenacity, +pybreaker
2. `app/tenants/models.py` — +ConsentLog model
3. `app/hik_gateway/models.py` — RawEvent dedupe_key index
4. `app/config/urls.py` — /legal/* routes
5. `app/tenants/auth_urls.py` — /auth/me/export, /auth/me, /auth/dpa routes
