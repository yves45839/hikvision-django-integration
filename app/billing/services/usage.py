"""Usage-based / metered billing: report consumption to Stripe."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from django.db import transaction
from django.utils import timezone

from ..models import Subscription, UsageRecord
from .stripe_client import get_stripe


@transaction.atomic
def report_usage(
    *,
    subscription: Subscription,
    quantity: int,
    timestamp: Optional[datetime] = None,
    action: str = "increment",
    idempotency_key: Optional[str] = None,
) -> UsageRecord:
    """Report `quantity` units of usage to the metered subscription item.

    Idempotency: callers can pass `idempotency_key` (e.g. an event_id) to
    guarantee that retries do not double-count usage.

    Returns the local UsageRecord row.
    """
    if not subscription.stripe_subscription_item_id:
        raise ValueError(
            f"Subscription {subscription.id} has no stripe_subscription_item_id "
            "(is the plan metered? has the webhook synced yet?)."
        )

    stripe = get_stripe()
    ts = timestamp or timezone.now()
    idem = idempotency_key or f"usage-{subscription.id}-{uuid.uuid4()}"

    record = stripe.SubscriptionItem.create_usage_record(
        subscription.stripe_subscription_item_id,
        quantity=int(quantity),
        timestamp=int(ts.timestamp()),
        action=action,
        idempotency_key=idem,
    )

    return UsageRecord.objects.create(
        tenant=subscription.tenant,
        subscription=subscription,
        stripe_subscription_item_id=subscription.stripe_subscription_item_id,
        stripe_usage_record_id=record.get("id", ""),
        quantity=int(quantity),
        timestamp=ts,
        action=action,
        idempotency_key=idem,
    )
