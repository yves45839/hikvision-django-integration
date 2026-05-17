"""One-time PaymentIntent creation — used by Stripe Elements (Payment Element)
on the frontend for an embedded (non-hosted) checkout experience.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import transaction

from tenants.models import Tenant

from ..models import Payment, PaymentIntentStatus
from .customers import get_or_create_customer
from .stripe_client import get_stripe


@transaction.atomic
def create_payment_intent(
    *,
    tenant: Tenant,
    amount_cents: int,
    currency: str = "eur",
    description: str = "",
    user=None,
    metadata: Optional[dict] = None,
) -> Payment:
    """Create a Stripe PaymentIntent and a local Payment row.

    Returns the local Payment object — caller can read `.metadata['client_secret']`
    on the Stripe response, but we expose the client_secret separately via the API.
    """
    stripe = get_stripe()
    customer = get_or_create_customer(tenant)

    base_metadata = {
        "tenant_id": str(tenant.id),
        "tenant_code": tenant.code,
    }
    if metadata:
        base_metadata.update({str(k): str(v) for k, v in metadata.items()})

    intent = stripe.PaymentIntent.create(
        amount=int(amount_cents),
        currency=currency,
        customer=customer.stripe_customer_id,
        description=description,
        metadata=base_metadata,
        automatic_payment_methods={"enabled": True},
    )

    payment = Payment.objects.create(
        tenant=tenant,
        customer=customer,
        stripe_payment_intent_id=intent["id"],
        amount=Decimal(amount_cents) / Decimal(100),
        currency=currency,
        status=intent.get("status") or PaymentIntentStatus.REQUIRES_PAYMENT_METHOD,
        description=description,
        metadata=base_metadata,
        created_by=user if user and getattr(user, "is_authenticated", False) else None,
    )

    # Stash the client_secret on the in-memory object so the view can return
    # it without an extra round-trip to Stripe.
    payment.client_secret = intent.get("client_secret", "")  # type: ignore[attr-defined]
    return payment
