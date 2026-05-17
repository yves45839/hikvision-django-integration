"""Sync Plan rows from Stripe (Products + Prices).

Usage:
    python manage.py sync_stripe_plans

Pulls all Stripe Prices that are active and have a Product, and upserts a
local `Plan` row per Price. Use `--dry-run` to preview.
"""
from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand

from billing.models import Plan, PlanInterval


class Command(BaseCommand):
    help = "Synchronize the Plan catalog from Stripe Products and Prices."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview without writing.")
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Also import inactive Stripe prices (default: active only).",
        )

    def handle(self, *args, **opts):
        from billing.services.stripe_client import get_stripe

        stripe = get_stripe()

        active_filter = None if opts["include_inactive"] else True
        prices = stripe.Price.list(limit=100, active=active_filter, expand=["data.product"])

        created = 0
        updated = 0
        for price in prices.auto_paging_iter():
            product = price.get("product") or {}
            if isinstance(product, str):
                product = stripe.Product.retrieve(product)

            recurring = price.get("recurring") or {}
            interval_raw = (recurring.get("interval") or "").lower()
            if interval_raw == "year":
                interval = PlanInterval.YEAR
            elif interval_raw == "month":
                interval = PlanInterval.MONTH
            else:
                interval = PlanInterval.ONE_TIME

            is_metered = (recurring.get("usage_type") or "") == "metered"

            unit_amount = price.get("unit_amount")
            amount = (
                Decimal(int(unit_amount)) / Decimal(100) if unit_amount is not None else Decimal("0.00")
            )

            meta = product.get("metadata") or {}
            code = meta.get("plan_code") or product.get("id") or price.get("id")

            # Optional metadata keys on the Stripe Product (set in dashboard):
            #   trial_period_days       e.g. "14"
            #   trial_requires_card     "true" / "false"  (default: false)
            #   device_quota            e.g. "10"
            #   event_quota_per_month   e.g. "10000"
            #   has_priority_support    "true" / "false"
            #   has_advanced_analytics  "true" / "false"
            def _bool(v: str | None, default: bool = False) -> bool:
                if v is None:
                    return default
                return str(v).strip().lower() in ("1", "true", "yes", "on")

            def _int(v: str | None, default: int) -> int:
                try:
                    return int(v) if v is not None else default
                except (TypeError, ValueError):
                    return default

            # Any product metadata key prefixed with `feat.` becomes a feature flag.
            # Example:
            #   feat.api_access        = true
            #   feat.multi_site        = true
            #   feat.retention_days    = 365
            features: dict = {}
            for key, value in meta.items():
                if not key.startswith("feat."):
                    continue
                feature_key = key[len("feat.") :]
                v = str(value).strip()
                # Try int → bool → str
                try:
                    features[feature_key] = int(v)
                    continue
                except (TypeError, ValueError):
                    pass
                if v.lower() in ("true", "false", "yes", "no", "1", "0", "on", "off"):
                    features[feature_key] = _bool(v, False)
                else:
                    features[feature_key] = v

            defaults = dict(
                name=product.get("name") or code,
                description=product.get("description") or "",
                stripe_product_id=product.get("id") or "",
                stripe_price_id=price.get("id") or "",
                amount=amount,
                currency=(price.get("currency") or "eur").lower(),
                interval=interval,
                is_metered=is_metered,
                metered_unit_label=(product.get("unit_label") or "") if is_metered else "",
                trial_period_days=_int(meta.get("trial_period_days"), 0),
                trial_requires_card=_bool(meta.get("trial_requires_card"), False),
                device_quota=_int(meta.get("device_quota"), 10),
                event_quota_per_month=_int(meta.get("event_quota_per_month"), 10_000),
                has_priority_support=_bool(meta.get("has_priority_support"), False),
                has_advanced_analytics=_bool(meta.get("has_advanced_analytics"), False),
                features=features,
                is_active=bool(price.get("active")) and bool(product.get("active")),
            )

            if opts["dry_run"]:
                self.stdout.write(self.style.NOTICE(f"[dry-run] {code}: {defaults}"))
                continue

            obj, was_created = Plan.objects.update_or_create(code=code, defaults=defaults)
            if was_created:
                created += 1
            else:
                updated += 1
            self.stdout.write(f"  {'+' if was_created else '~'} {obj.code} ({obj.stripe_price_id})")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. created={created} updated={updated}"
                f"{' (dry-run)' if opts['dry_run'] else ''}"
            )
        )
