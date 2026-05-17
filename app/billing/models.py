"""
Billing models — Stripe-backed subscriptions, one-time payments, and usage billing.

Architecture:
- Plan        : catalog of subscription plans (mirrored from Stripe Products / Prices).
- Customer    : 1-to-1 with Tenant; stores the Stripe customer_id for the tenant.
- Subscription: active / canceled / past_due Stripe subscription for a tenant.
- Invoice     : mirrored Stripe invoices (paid, open, void).
- Payment     : one-time payments (PaymentIntent) — installation fees, device purchases, etc.
- UsageRecord : metered usage (e.g. number of access events, devices, doors) reported to Stripe.

Stripe is the source of truth — these models are a local cache + audit log so the dashboard
can render data without hitting the Stripe API on every request.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from tenants.models import Tenant


# ---------------------------------------------------------------------------
# Plan catalog
# ---------------------------------------------------------------------------

class PlanInterval(models.TextChoices):
    MONTH = "month", "Mensuel"
    YEAR = "year", "Annuel"
    ONE_TIME = "one_time", "Paiement unique"


class Plan(models.Model):
    """A subscription plan or one-time-purchase product mirrored from Stripe.

    Map onto a Stripe Product (`stripe_product_id`) and a single Price
    (`stripe_price_id`). Store usage limits locally so we can enforce them
    without calling Stripe on every request.
    """

    code = models.SlugField(max_length=64, unique=True, help_text="basic, pro, enterprise, ...")
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True, default="")

    # Stripe references
    stripe_product_id = models.CharField(max_length=255, blank=True, default="")
    stripe_price_id = models.CharField(max_length=255, blank=True, default="")

    # Pricing (denormalized from Stripe for display)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=8, default="eur")
    interval = models.CharField(
        max_length=16,
        choices=PlanInterval.choices,
        default=PlanInterval.MONTH,
    )

    # Quotas & feature flags (used by the app)
    device_quota = models.PositiveIntegerField(default=10)
    event_quota_per_month = models.PositiveIntegerField(default=10_000)
    has_priority_support = models.BooleanField(default=False)
    has_advanced_analytics = models.BooleanField(default=False)

    # Metered billing
    is_metered = models.BooleanField(
        default=False,
        help_text="If true, this price uses Stripe usage-based billing.",
    )
    metered_unit_label = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="e.g. 'event', 'device', 'door' — only when is_metered=True.",
    )

    # Free trial — number of days; 0 = no trial. When > 0, Checkout will start
    # the subscription in `trialing` status. Combined with `trial_requires_card`
    # we can offer a frictionless "no credit card required" trial.
    trial_period_days = models.PositiveIntegerField(
        default=0,
        help_text="Free trial length in days. 0 disables the trial.",
    )
    trial_requires_card = models.BooleanField(
        default=False,
        help_text=(
            "If False and trial_period_days > 0, Stripe Checkout will set "
            "payment_method_collection='if_required' so the card is optional."
        ),
    )

    # Free-form feature flags — checked client-side by <FeatureGate>.
    # Example payload for the Pro plan:
    #   {"api_access": true, "advanced_analytics": true, "multi_site": true,
    #    "white_label": false, "sso": false, "retention_days": 365}
    # The frontend hook `useTenantPlan` exposes this verbatim.
    features = models.JSONField(
        default=dict,
        blank=True,
        help_text="Feature flags for this plan. Used by the frontend FeatureGate component.",
    )

    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "amount")
        indexes = [
            models.Index(fields=["is_active", "sort_order"]),
            models.Index(fields=["stripe_price_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


# ---------------------------------------------------------------------------
# Customer (1-to-1 with Tenant)
# ---------------------------------------------------------------------------

class Customer(models.Model):
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="billing_customer",
    )
    stripe_customer_id = models.CharField(max_length=255, unique=True)

    email = models.EmailField(blank=True, default="")
    name = models.CharField(max_length=255, blank=True, default="")
    default_payment_method_id = models.CharField(max_length=255, blank=True, default="")

    livemode = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["stripe_customer_id"]),
        ]

    def __str__(self) -> str:
        return f"Customer<{self.tenant.code}:{self.stripe_customer_id}>"


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------

class SubscriptionStatus(models.TextChoices):
    INCOMPLETE = "incomplete", "Incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired", "Incomplete expired"
    TRIALING = "trialing", "Trialing"
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Past due"
    CANCELED = "canceled", "Canceled"
    UNPAID = "unpaid", "Unpaid"
    PAUSED = "paused", "Paused"


class Subscription(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="subscriptions")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")

    stripe_subscription_id = models.CharField(max_length=255, unique=True)
    stripe_subscription_item_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Item id used to report usage for metered subscriptions.",
    )

    status = models.CharField(
        max_length=32,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.INCOMPLETE,
    )

    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)

    livemode = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["status", "current_period_end"]),
        ]

    def __str__(self) -> str:
        return f"Sub<{self.tenant.code}:{self.plan.code}:{self.status}>"

    @property
    def is_active(self) -> bool:
        return self.status in {
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.TRIALING,
        }


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------

class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    OPEN = "open", "Open"
    PAID = "paid", "Paid"
    UNCOLLECTIBLE = "uncollectible", "Uncollectible"
    VOID = "void", "Void"


class Invoice(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="invoices")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="invoices")
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )

    stripe_invoice_id = models.CharField(max_length=255, unique=True)
    number = models.CharField(max_length=64, blank=True, default="")

    status = models.CharField(max_length=32, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT)

    amount_due = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    amount_remaining = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=8, default="eur")

    hosted_invoice_url = models.URLField(blank=True, default="")
    invoice_pdf = models.URLField(blank=True, default="")

    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["customer", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"Invoice<{self.number or self.stripe_invoice_id}:{self.status}>"


# ---------------------------------------------------------------------------
# One-time Payment (PaymentIntent)
# ---------------------------------------------------------------------------

class PaymentIntentStatus(models.TextChoices):
    REQUIRES_PAYMENT_METHOD = "requires_payment_method", "Requires payment method"
    REQUIRES_CONFIRMATION = "requires_confirmation", "Requires confirmation"
    REQUIRES_ACTION = "requires_action", "Requires action"
    PROCESSING = "processing", "Processing"
    SUCCEEDED = "succeeded", "Succeeded"
    REQUIRES_CAPTURE = "requires_capture", "Requires capture"
    CANCELED = "canceled", "Canceled"


class Payment(models.Model):
    """One-time payment via Stripe PaymentIntent (Stripe Elements / Payment Element).

    Used for non-recurring charges: setup fees, hardware sales, premium add-ons.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="payments")
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )

    stripe_payment_intent_id = models.CharField(max_length=255, unique=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=8, default="eur")

    status = models.CharField(
        max_length=32,
        choices=PaymentIntentStatus.choices,
        default=PaymentIntentStatus.REQUIRES_PAYMENT_METHOD,
    )

    description = models.CharField(max_length=255, blank=True, default="")
    receipt_url = models.URLField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="initiated_payments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"Payment<{self.tenant.code}:{self.amount}{self.currency}:{self.status}>"


# ---------------------------------------------------------------------------
# Usage records (metered billing)
# ---------------------------------------------------------------------------

class UsageRecord(models.Model):
    """Metered billing: records reported to Stripe via subscription_item usage_records.

    For the access-control SaaS this could be e.g. one record per door scan / event,
    or aggregated daily counts (devices online * 24h).
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="usage_records")
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="usage_records",
    )
    stripe_usage_record_id = models.CharField(max_length=255, blank=True, default="")
    stripe_subscription_item_id = models.CharField(max_length=255)

    quantity = models.PositiveIntegerField()
    timestamp = models.DateTimeField(default=timezone.now)
    action = models.CharField(
        max_length=16,
        default="increment",
        help_text='Stripe usage action: "increment" (default) or "set".',
    )
    idempotency_key = models.CharField(max_length=255, blank=True, default="", db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-timestamp",)
        indexes = [
            models.Index(fields=["tenant", "-timestamp"]),
            models.Index(fields=["subscription", "-timestamp"]),
        ]

    def __str__(self) -> str:
        return f"Usage<{self.tenant.code}:{self.quantity}@{self.timestamp:%Y-%m-%d}>"


# ---------------------------------------------------------------------------
# Webhook event log (idempotency)
# ---------------------------------------------------------------------------

class WebhookEvent(models.Model):
    """Audit trail of Stripe webhook events — also enforces idempotency
    (we won't process the same event twice).
    """

    stripe_event_id = models.CharField(max_length=255, unique=True)
    type = models.CharField(max_length=128, db_index=True)
    livemode = models.BooleanField(default=False)
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True, default="")
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-received_at",)
        indexes = [
            models.Index(fields=["type", "-received_at"]),
            models.Index(fields=["processed", "-received_at"]),
        ]

    def __str__(self) -> str:
        return f"Webhook<{self.type}:{self.stripe_event_id}>"
