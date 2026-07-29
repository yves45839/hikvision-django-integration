"""Moteur de décision du pointage mobile — pur, sans DRF ni requête HTTP.

Politique GPS (v1 — contrôle de proximité, pas antifraude) :
- précision > MAX_ACCURACY_M → refus ACCURACY_TOO_LOW ;
- distance ≤ rayon → zone "inside" (acceptation normale) ;
- rayon < distance ≤ rayon + BORDERLINE_GRACE_M et précision ≤ BORDERLINE_MAX_ACCURACY_M
  → zone "borderline" (accepté, marqué) ;
- sinon → "outside", refus OUT_OF_ZONE avec le site le plus proche.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Sequence

from presence.geo import haversine_m

ACTION_CHECK_IN = "CHECK_IN"
ACTION_CHECK_OUT = "CHECK_OUT"


@dataclass(frozen=True)
class SitePoint:
    id: int
    name: str
    latitude: float
    longitude: float
    radius_m: int


@dataclass(frozen=True)
class PunchAttempt:
    latitude: float
    longitude: float
    accuracy_m: float
    action: str | None = None  # action affichée par l'app ; None = suivre la suggestion


@dataclass(frozen=True)
class PunchContext:
    server_now: datetime
    sites: Sequence[SitePoint]
    last_punch_action: str | None  # dernier pointage du jour, toutes sources
    last_punch_at: datetime | None
    max_accuracy_m: float = 150.0
    borderline_grace_m: float = 20.0
    borderline_max_accuracy_m: float = 50.0
    min_interval_seconds: int = 60


@dataclass(frozen=True)
class PunchDecision:
    verdict: str  # "accepted" | "rejected"
    error_code: str | None = None
    action: str | None = None
    suggested_action: str | None = None
    site: SitePoint | None = None
    distance_m: float | None = None
    tolerance_m: float | None = None
    zone: str | None = None  # inside | borderline | outside
    nearest_site: SitePoint | None = None
    retry_after_s: int | None = None
    extra: dict = field(default_factory=dict)


def suggested_action(last_punch_action: str | None) -> str:
    return ACTION_CHECK_OUT if last_punch_action == ACTION_CHECK_IN else ACTION_CHECK_IN


def evaluate_mobile_punch(attempt: PunchAttempt, context: PunchContext) -> PunchDecision:
    """Évalue une tentative de pointage. Ne touche ni la base ni l'horloge :
    tout l'état nécessaire arrive via ``context`` (testable en isolation)."""
    if not (-90.0 <= attempt.latitude <= 90.0 and -180.0 <= attempt.longitude <= 180.0):
        return PunchDecision(verdict="rejected", error_code="INVALID_COORDINATES")

    if attempt.accuracy_m is None or attempt.accuracy_m < 0:
        return PunchDecision(verdict="rejected", error_code="INVALID_COORDINATES")

    if attempt.accuracy_m > context.max_accuracy_m:
        return PunchDecision(
            verdict="rejected",
            error_code="ACCURACY_TOO_LOW",
            extra={"max_accuracy_m": context.max_accuracy_m},
        )

    if not context.sites:
        return PunchDecision(verdict="rejected", error_code="NO_SITE_CONFIGURED")

    # Meilleur site : zone la plus favorable puis distance minimale.
    best: tuple[int, float, SitePoint, str] | None = None  # (rang zone, dist, site, zone)
    nearest: tuple[float, SitePoint] | None = None
    for site in context.sites:
        distance = haversine_m(attempt.latitude, attempt.longitude, site.latitude, site.longitude)
        if nearest is None or distance < nearest[0]:
            nearest = (distance, site)
        if distance <= site.radius_m:
            zone, rank = "inside", 0
        elif (
            distance <= site.radius_m + context.borderline_grace_m
            and attempt.accuracy_m <= context.borderline_max_accuracy_m
        ):
            zone, rank = "borderline", 1
        else:
            continue
        if best is None or (rank, distance) < (best[0], best[1]):
            best = (rank, distance, site, zone)

    if best is None:
        nearest_distance, nearest_site = nearest
        return PunchDecision(
            verdict="rejected",
            error_code="OUT_OF_ZONE",
            nearest_site=nearest_site,
            distance_m=round(nearest_distance, 1),
            tolerance_m=float(nearest_site.radius_m)
            + (
                context.borderline_grace_m
                if attempt.accuracy_m <= context.borderline_max_accuracy_m
                else 0.0
            ),
        )

    _, distance, site, zone = best

    if context.last_punch_at is not None:
        elapsed = (context.server_now - context.last_punch_at).total_seconds()
        if elapsed < context.min_interval_seconds:
            return PunchDecision(
                verdict="rejected",
                error_code="TOO_SOON",
                retry_after_s=max(1, int(context.min_interval_seconds - elapsed)),
            )

    server_suggestion = suggested_action(context.last_punch_action)
    if attempt.action is not None and attempt.action != server_suggestion:
        return PunchDecision(
            verdict="rejected",
            error_code="SUGGESTED_ACTION_CHANGED",
            suggested_action=server_suggestion,
        )

    return PunchDecision(
        verdict="accepted",
        action=server_suggestion,
        site=site,
        distance_m=round(distance, 1),
        tolerance_m=float(site.radius_m),
        zone=zone,
    )
