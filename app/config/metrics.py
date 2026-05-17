"""Prometheus metrics for Phase 7 — Observabilité."""

from prometheus_client import Counter, Histogram, Gauge

# Événements Hikvision
hik_events_received_total = Counter(
    "hik_events_received_total",
    "Nombre total d'événements Hikvision reçus via webhook",
    ["tenant_code", "event_type"],
)
hik_events_processing_seconds = Histogram(
    "hik_events_processing_seconds",
    "Temps de traitement d'un événement Hikvision",
    ["tenant_code"],
)

# Push gateway
gateway_push_total = Counter(
    "gateway_push_total",
    "Nombre total de push employés vers la gateway",
    ["tenant_code", "status"],  # status: success | failure
)
gateway_push_duration_seconds = Histogram(
    "gateway_push_duration_seconds",
    "Durée d'un push gateway",
    ["tenant_code"],
)

# Onboardings
device_onboarding_total = Counter(
    "device_onboarding_total",
    "Nombre total de jobs d'onboarding device",
    ["tenant_code", "status"],  # status: started | success | failure
)

# Tenants actifs
active_tenants_gauge = Gauge(
    "active_tenants_total",
    "Nombre de tenants actifs",
)

# Signups
tenant_signups_total = Counter(
    "tenant_signups_total",
    "Nombre total de signups tenant",
)
