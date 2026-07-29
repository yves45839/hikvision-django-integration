"""Tests du moteur de décision pur (Phase 3) — aucune base de données."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

from django.test import SimpleTestCase

from presence.punch_engine import (
    PunchAttempt,
    PunchContext,
    SitePoint,
    evaluate_mobile_punch,
    suggested_action,
)

NOW = datetime(2026, 7, 29, 8, 0, tzinfo=dt_timezone.utc)
# Site au Plateau, Abidjan ; ~111 m ≈ 0.001° de latitude.
SITE = SitePoint(id=1, name="Siège", latitude=5.3485, longitude=-4.0277, radius_m=100)


def ctx(**overrides) -> PunchContext:
    defaults = dict(
        server_now=NOW,
        sites=[SITE],
        last_punch_action=None,
        last_punch_at=None,
    )
    defaults.update(overrides)
    return PunchContext(**defaults)


def attempt(lat_offset_deg=0.0, accuracy=10.0, action=None) -> PunchAttempt:
    return PunchAttempt(
        latitude=SITE.latitude + lat_offset_deg,
        longitude=SITE.longitude,
        accuracy_m=accuracy,
        action=action,
    )


class EvaluatePunchTests(SimpleTestCase):
    def test_inside_accepted(self):
        decision = evaluate_mobile_punch(attempt(lat_offset_deg=0.0005), ctx())  # ~55 m
        self.assertEqual(decision.verdict, "accepted")
        self.assertEqual(decision.zone, "inside")
        self.assertEqual(decision.action, "CHECK_IN")
        self.assertAlmostEqual(decision.distance_m, 55.3, delta=1.5)

    def test_borderline_accepted_with_good_accuracy(self):
        # ~111 m : hors rayon (100) mais dans la grâce (120) avec précision ≤ 50.
        decision = evaluate_mobile_punch(attempt(lat_offset_deg=0.001, accuracy=30), ctx())
        self.assertEqual(decision.verdict, "accepted")
        self.assertEqual(decision.zone, "borderline")

    def test_borderline_rejected_with_poor_accuracy(self):
        decision = evaluate_mobile_punch(attempt(lat_offset_deg=0.001, accuracy=80), ctx())
        self.assertEqual(decision.verdict, "rejected")
        self.assertEqual(decision.error_code, "OUT_OF_ZONE")

    def test_outside_rejected_with_nearest_site(self):
        decision = evaluate_mobile_punch(attempt(lat_offset_deg=0.01), ctx())  # ~1.1 km
        self.assertEqual(decision.error_code, "OUT_OF_ZONE")
        self.assertEqual(decision.nearest_site.id, SITE.id)
        self.assertGreater(decision.distance_m, 1000)
        self.assertEqual(decision.tolerance_m, 120.0)  # rayon + grâce (précision 10 ≤ 50)

    def test_accuracy_too_low(self):
        decision = evaluate_mobile_punch(attempt(accuracy=200), ctx())
        self.assertEqual(decision.error_code, "ACCURACY_TOO_LOW")
        self.assertEqual(decision.extra["max_accuracy_m"], 150.0)

    def test_invalid_coordinates(self):
        bad = PunchAttempt(latitude=95.0, longitude=0.0, accuracy_m=10)
        self.assertEqual(evaluate_mobile_punch(bad, ctx()).error_code, "INVALID_COORDINATES")

    def test_no_site_configured(self):
        decision = evaluate_mobile_punch(attempt(), ctx(sites=[]))
        self.assertEqual(decision.error_code, "NO_SITE_CONFIGURED")

    def test_too_soon(self):
        decision = evaluate_mobile_punch(
            attempt(),
            ctx(last_punch_action="CHECK_IN", last_punch_at=NOW - timedelta(seconds=20)),
        )
        self.assertEqual(decision.error_code, "TOO_SOON")
        self.assertEqual(decision.retry_after_s, 40)

    def test_toggle_check_out_after_check_in(self):
        decision = evaluate_mobile_punch(
            attempt(),
            ctx(last_punch_action="CHECK_IN", last_punch_at=NOW - timedelta(hours=4)),
        )
        self.assertEqual(decision.action, "CHECK_OUT")

    def test_stale_ui_action_conflict(self):
        decision = evaluate_mobile_punch(
            attempt(action="CHECK_IN"),
            ctx(last_punch_action="CHECK_IN", last_punch_at=NOW - timedelta(hours=1)),
        )
        self.assertEqual(decision.error_code, "SUGGESTED_ACTION_CHANGED")
        self.assertEqual(decision.suggested_action, "CHECK_OUT")

    def test_best_site_wins_when_overlapping(self):
        near = SitePoint(id=2, name="Annexe", latitude=SITE.latitude + 0.0002, longitude=SITE.longitude, radius_m=100)
        decision = evaluate_mobile_punch(attempt(lat_offset_deg=0.0002), ctx(sites=[SITE, near]))
        self.assertEqual(decision.site.id, near.id)

    def test_suggested_action_helper(self):
        self.assertEqual(suggested_action(None), "CHECK_IN")
        self.assertEqual(suggested_action("CHECK_OUT"), "CHECK_IN")
        self.assertEqual(suggested_action("CHECK_IN"), "CHECK_OUT")
