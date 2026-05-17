"""Tenant <-> Stripe customer mapping."""
from __future__ import annotations

from typing import Optional

from django.db import transaction

from tenants.models import Tenant

from ..models import Customer
from .stripe_client import get_stripe


@transaction.atomic
def get_or_create_customer(
    tenant: Tenant,
    *,
    email: Optional[str] = None,
    name: Optional[str] = None,
) -> Customer:
    """Return the local Customer for `tenant`, creating it (and the Stripe
    customer) if missing.

    This is idempotent — if the tenant already has a Customer row we just
    return it without calling Stripe again.
    """
    try:
        return tenant.billing_customer
    except Customer.DoesNotExist:
        pass

    stripe = get_stripe()

    stripe_customer = stripe.Customer.create(
        email=email or "",
        name=name or tenant.name,
        metadata={
            "tenant_id": str(tenant.id),
            "tenant_code": tenant.code,
        },
    )

    return Customer.objects.create(
        tenant=tenant,
        stripe_customer_id=stripe_customer["id"],
        email=email or "",
        name=name or tenant.name,
        livemode=bool(stripe_customer.get("livemode", False)),
    )
