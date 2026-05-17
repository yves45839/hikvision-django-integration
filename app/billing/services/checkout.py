"""Stripe Checkout sessions (hosted checkout) and Billing Portal sessions."""
from __future__ import annotations

from typing import Optional

from django.conf import settings

from tenants.models import Tenant

from ..models import Plan
from .customers import get_or_create_customer
from .stripe_client import get_stripe


def _frontend_url() -> str:
    return getattr(settings, "FRONTEND_AUTH_BASE_URL", "http://localhost:3000").rstrip("/")


def create_checkout_session_subscription(
    *,
    tenant: Tenant,
    plan: Plan,
    user_email: Optional[str] = None,
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
    trial_period_days: Optional[int] = None,
    locale: Optional[str] = None,
) -> dict:
    """Create a Stripe Checkout Session in subscription mode for `plan`.

    Trial behaviour
    ---------------
    - If ``trial_period_days`` is None, fall back to ``plan.trial_period_days``.
    - When the resolved trial is > 0 AND ``plan.trial_requires_card`` is False,
      Checkout uses ``payment_method_collection='if_required'`` so the user can
      start the trial without entering a card. Stripe will request the card
      automatically before the first real charge.

    Returns the Stripe response dict (callers usually only need `id` and `url`).
    """
    if not plan.stripe_price_id:
        raise ValueError(f"Plan {plan.code} has no stripe_price_id configured.")

    stripe = get_stripe()
    customer = get_or_create_customer(tenant, email=user_email)

    base = _frontend_url()
    success_url = success_url or f"{base}/billing?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = cancel_url or f"{base}/billing?checkout=cancel"

    line_item = {"price": plan.stripe_price_id}
    # Metered prices must NOT include quantity (Stripe will reject it)
    if not plan.is_metered:
        line_item["quantity"] = 1

    # ---- Resolve trial duration ----
    resolved_trial = (
        int(trial_period_days)
        if trial_period_days is not None
        else int(getattr(plan, "trial_period_days", 0) or 0)
    )

    subscription_data: dict = {
        "metadata": {
            "tenant_id": str(tenant.id),
            "tenant_code": tenant.code,
            "plan_code": plan.code,
        },
    }
    if resolved_trial > 0:
        subscription_data["trial_period_days"] = resolved_trial

    # ---- Build the Checkout payload ----
    create_kwargs: dict = dict(
        mode="subscription",
        customer=customer.stripe_customer_id,
        line_items=[line_item],
        success_url=success_url,
        cancel_url=cancel_url,
        allow_promotion_codes=True,
        subscription_data=subscription_data,
        client_reference_id=str(tenant.id),
        metadata={
            "tenant_id": str(tenant.id),
            "tenant_code": tenant.code,
            "plan_code": plan.code,
        },
        # Let Stripe localize the Checkout page (FR/EN/etc) automatically
        locale=(locale or "auto"),
    )

    # Optional: enable Stripe Tax (auto-VAT) if configured globally
    if getattr(settings, "STRIPE_AUTOMATIC_TAX", False):
        create_kwargs["automatic_tax"] = {"enabled": True}

    # Frictionless trial → don't ask for a card up-front
    if resolved_trial > 0 and not getattr(plan, "trial_requires_card", False):
        create_kwargs["payment_method_collection"] = "if_required"
        # If no card is added before trial end, cancel rather than retry-charge
        subscription_data["trial_settings"] = {
            "end_behavior": {"missing_payment_method": "cancel"},
        }

    session = stripe.checkout.Session.create(**create_kwargs)
    return session


def create_checkout_session_one_time(
    *,
    tenant: Tenant,
    amount_cents: int,
    currency: str = "eur",
    description: str = "",
    user_email: Optional[str] = None,
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
) -> dict:
    """Create a one-time Checkout Session (no subscription) — e.g. install fee."""
    stripe = get_stripe()
    customer = get_or_create_customer(tenant, email=user_email)

    base = _frontend_url()
    success_url = success_url or f"{base}/billing?payment=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = cancel_url or f"{base}/billing?payment=cancel"

    session = stripe.checkout.Session.create(
        mode="payment",
        customer=customer.stripe_customer_id,
        line_items=[
            {
                "price_data": {
                    "currency": currency,
                    "product_data": {
                        "name": description or "Paiement",
                    },
                    "unit_amount": int(amount_cents),
                },
                "quantity": 1,
            }
        ],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=str(tenant.id),
        metadata={
            "tenant_id": str(tenant.id),
            "tenant_code": tenant.code,
            "kind": "one_time",
        },
    )
    return session


def create_billing_portal_session(
    *,
    tenant: Tenant,
    return_url: Optional[str] = None,
) -> dict:
    """Create a Stripe Customer Portal session — the hosted page that lets
    customers manage their subscription, payment methods, and invoices.
    """
    stripe = get_stripe()
    customer = get_or_create_customer(tenant)

    base = _frontend_url()
    return_url = return_url or f"{base}/billing"

    session = stripe.billing_portal.Session.create(
        customer=customer.stripe_customer_id,
        return_url=return_url,
    )
    return session
