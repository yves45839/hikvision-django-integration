"""Stripe webhook handler — keeps local DB in sync with Stripe and notifies tenants by email.

Events we react to:
- checkout.session.completed         -> subscription/payment was set up successfully
- customer.subscription.created      -> create local Subscription
- customer.subscription.updated      -> update status, period, plan
- customer.subscription.deleted      -> mark canceled
- invoice.paid                       -> mark invoice paid, sync subscription
- invoice.payment_failed             -> log failure, mark past_due
- payment_intent.succeeded           -> update Payment row
- payment_intent.payment_failed      -> update Payment row
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_tz
from decimal import Decimal
from typing import Any, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from tenants.models import Tenant, TenantMembership, TenantRole
from tenants.emails import send_payment_failed_email, send_payment_success_email

from .models import (
    Customer,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentIntentStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
    WebhookEvent,
)

logger = logging.getLogger(__name__)


def _ts(value: Any) -> Optional[datetime]:
    """Stripe timestamps are UNIX seconds. Convert to aware datetime."""
    if value in (None, 0, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=dt_tz.utc)
    except (TypeError, ValueError):
        return None


def _amount(value: Any) -> Decimal:
    """Stripe amounts are in cents. Convert to Decimal euros/dollars."""
    try:
        return (Decimal(int(value or 0)) / Decimal(100)).quantize(Decimal("0.01"))
    except (TypeError, ValueError):
        return Decimal("0.00")


def _resolve_tenant(metadata: dict) -> Optional[Tenant]:
    tenant_id = metadata.get("tenant_id")
    if tenant_id:
        try:
            return Tenant.objects.get(id=int(tenant_id))
        except (Tenant.DoesNotExist, ValueError, TypeError):
            pass
    code = metadata.get("tenant_code")
    if code:
        try:
            return Tenant.objects.get(code=code)
        except Tenant.DoesNotExist:
            pass
    return None


def _resolve_customer(stripe_customer_id: str) -> Optional[Customer]:
    if not stripe_customer_id:
        return None
    return Customer.objects.filter(stripe_customer_id=stripe_customer_id).first()


def _resolve_plan(price_id: str) -> Optional[Plan]:
    if not price_id:
        return None
    return Plan.objects.filter(stripe_price_id=price_id, is_active=True).first()


def _billing_recipient(customer: Customer) -> tuple[str, str]:
    """Pick the best recipient email + first name for billing notifications.

    Order of preference: Customer.email → first tenant_admin user.
    Returns ("", "") when nothing is found, in which case the caller
    should skip sending.
    """
    customer_email = str(getattr(customer, "email", "") or "").strip()
    if customer_email and "@" in customer_email:
        # Try to find a matching user for the first name; ignore on miss.
        admin_first_name = ""
        admin = (
            TenantMembership.objects.select_related("user")
            .filter(tenant=customer.tenant, role=TenantRole.TENANT_ADMIN, user__email__iexact=customer_email)
            .first()
        )
        if admin and getattr(admin.user, "first_name", ""):
            admin_first_name = admin.user.first_name
        return customer_email, admin_first_name

    admin_membership = (
        TenantMembership.objects.select_related("user")
        .filter(tenant=customer.tenant, role=TenantRole.TENANT_ADMIN, user__is_active=True)
        .order_by("id")
        .first()
    )
    if admin_membership and admin_membership.user.email:
        return admin_membership.user.email, getattr(admin_membership.user, "first_name", "") or ""

    return "", ""


def _retry_url() -> str:
    base_url = str(getattr(settings, "FRONTEND_AUTH_BASE_URL", "") or "").strip().rstrip("/")
    return f"{base_url}/billing" if base_url else ""


# ---------------------------------------------------------------------------
# Subscription handlers
# ---------------------------------------------------------------------------

@transaction.atomic
def handle_subscription_event(event_type: str, sub_obj: dict) -> None:
    stripe_sub_id = sub_obj.get("id")
    if not stripe_sub_id:
        return

    items = (sub_obj.get("items") or {}).get("data") or []
    first_item = items[0] if items else {}
    price_id = (first_item.get("price") or {}).get("id", "")
    plan = _resolve_plan(price_id)

    customer = _resolve_customer(sub_obj.get("customer", ""))
    tenant = customer.tenant if customer else _resolve_tenant(sub_obj.get("metadata") or {})

    if not (customer and tenant and plan):
        logger.warning(
            "Subscription webhook missing local references "
            "(customer=%s, tenant=%s, plan=%s, sub_id=%s)",
            bool(customer), bool(tenant), bool(plan), stripe_sub_id,
        )
        if event_type == "customer.subscription.deleted":
            Subscription.objects.filter(stripe_subscription_id=stripe_sub_id).update(
                status=SubscriptionStatus.CANCELED,
                canceled_at=timezone.now(),
            )
        return

    defaults = {
        "tenant": tenant,
        "customer": customer,
        "plan": plan,
        "stripe_subscription_item_id": first_item.get("id", ""),
        "status": sub_obj.get("status") or SubscriptionStatus.INCOMPLETE,
        "current_period_start": _ts(sub_obj.get("current_period_start")),
        "current_period_end": _ts(sub_obj.get("current_period_end")),
        "trial_end": _ts(sub_obj.get("trial_end")),
        "cancel_at_period_end": bool(sub_obj.get("cancel_at_period_end")),
        "canceled_at": _ts(sub_obj.get("canceled_at")),
        "livemode": bool(sub_obj.get("livemode")),
        "metadata": sub_obj.get("metadata") or {},
    }

    Subscription.objects.update_or_create(
        stripe_subscription_id=stripe_sub_id,
        defaults=defaults,
    )

    # Mirror status onto the Tenant for quick lookups
    if defaults["status"] in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING}:
        Tenant.objects.filter(id=tenant.id).update(
            payment_status="paid",
            is_active=True,
            device_quota=plan.device_quota,
        )
    elif defaults["status"] == SubscriptionStatus.PAST_DUE:
        Tenant.objects.filter(id=tenant.id).update(payment_status="failed")
    elif defaults["status"] in {SubscriptionStatus.CANCELED, SubscriptionStatus.UNPAID}:
        Tenant.objects.filter(id=tenant.id).update(payment_status="pending")


# ---------------------------------------------------------------------------
# Invoice handlers
# ---------------------------------------------------------------------------

@transaction.atomic
def handle_invoice_event(event_type: str, inv_obj: dict) -> None:
    stripe_inv_id = inv_obj.get("id")
    if not stripe_inv_id:
        return

    customer = _resolve_customer(inv_obj.get("customer", ""))
    if not customer:
        logger.warning("Invoice webhook for unknown customer: %s", inv_obj.get("customer"))
        return

    subscription = None
    sub_id = inv_obj.get("subscription")
    if sub_id:
        subscription = Subscription.objects.filter(stripe_subscription_id=sub_id).first()

    paid_at = None
    if event_type == "invoice.paid" or inv_obj.get("status") == InvoiceStatus.PAID:
        paid_at = _ts(inv_obj.get("status_transitions", {}).get("paid_at")) or timezone.now()

    invoice, _ = Invoice.objects.update_or_create(
        stripe_invoice_id=stripe_inv_id,
        defaults={
            "tenant": customer.tenant,
            "customer": customer,
            "subscription": subscription,
            "number": inv_obj.get("number") or "",
            "status": inv_obj.get("status") or InvoiceStatus.DRAFT,
            "amount_due": _amount(inv_obj.get("amount_due")),
            "amount_paid": _amount(inv_obj.get("amount_paid")),
            "amount_remaining": _amount(inv_obj.get("amount_remaining")),
            "currency": inv_obj.get("currency") or "eur",
            "hosted_invoice_url": inv_obj.get("hosted_invoice_url") or "",
            "invoice_pdf": inv_obj.get("invoice_pdf") or "",
            "period_start": _ts(inv_obj.get("period_start")),
            "period_end": _ts(inv_obj.get("period_end")),
            "paid_at": paid_at,
        },
    )

    if event_type == "invoice.payment_failed" and subscription:
        Tenant.objects.filter(id=subscription.tenant_id).update(payment_status="failed")

    # ---- Notify the customer by email -------------------------------------
    # Use a separate try/except so that a mailing failure doesn't break the
    # webhook processing (Stripe would otherwise retry forever).
    try:
        recipient_email, recipient_first_name = _billing_recipient(customer)
        if recipient_email:
            plan_name = ""
            if subscription and subscription.plan:
                plan_name = subscription.plan.name

            if event_type == "invoice.paid":
                send_payment_success_email(
                    to_email=recipient_email,
                    first_name=recipient_first_name,
                    tenant_name=customer.tenant.name,
                    plan_name=plan_name,
                    amount=str(invoice.amount_paid or invoice.amount_due),
                    currency=(invoice.currency or "eur").upper(),
                    invoice_number=invoice.number,
                    invoice_url=invoice.hosted_invoice_url,
                    invoice_pdf=invoice.invoice_pdf,
                    paid_at=invoice.paid_at,
                    period_start=invoice.period_start,
                    period_end=invoice.period_end,
                )
            elif event_type == "invoice.payment_failed":
                # Stripe usually exposes the reason on the latest charge / last_payment_error.
                failure_reason = ""
                last_error = (
                    inv_obj.get("last_finalization_error")
                    or inv_obj.get("last_payment_error")
                    or {}
                )
                if isinstance(last_error, dict):
                    failure_reason = str(last_error.get("message") or "").strip()
                send_payment_failed_email(
                    to_email=recipient_email,
                    first_name=recipient_first_name,
                    tenant_name=customer.tenant.name,
                    amount=str(invoice.amount_due or invoice.amount_remaining),
                    currency=(invoice.currency or "eur").upper(),
                    invoice_number=invoice.number,
                    failure_reason=failure_reason,
                    retry_url=invoice.hosted_invoice_url or _retry_url(),
                    attempted_at=timezone.now(),
                )
    except Exception:  # pragma: no cover — never break webhook processing for an email error.
        logger.exception("Failed to send billing notification email for invoice=%s", stripe_inv_id)


# ---------------------------------------------------------------------------
# PaymentIntent handlers (Stripe Elements / one-time payments)
# ---------------------------------------------------------------------------

@transaction.atomic
def handle_payment_intent_event(event_type: str, pi_obj: dict) -> None:
    stripe_pi_id = pi_obj.get("id")
    if not stripe_pi_id:
        return

    payment = Payment.objects.filter(stripe_payment_intent_id=stripe_pi_id).first()
    if not payment:
        # Could be a Stripe-side payment we never registered locally — skip silently.
        logger.info("PaymentIntent webhook for unknown PI: %s", stripe_pi_id)
        return

    payment.status = pi_obj.get("status") or payment.status

    charges = (pi_obj.get("charges") or {}).get("data") or []
    if charges:
        receipt_url = charges[0].get("receipt_url") or ""
        if receipt_url:
            payment.receipt_url = receipt_url

    payment.save(update_fields=["status", "receipt_url", "updated_at"])


# ---------------------------------------------------------------------------
# Checkout session completed
# ---------------------------------------------------------------------------

@transaction.atomic
def handle_checkout_completed(session_obj: dict) -> None:
    """Right after the customer finishes the hosted Checkout flow.

    The subscription/payment_intent created here will also fire its own
    `customer.subscription.created` / `payment_intent.succeeded` event,
    so the actual data sync happens there. We use this event to mark the
    tenant as paid for fast UX feedback.
    """
    metadata = session_obj.get("metadata") or {}
    tenant = _resolve_tenant(metadata)
    if tenant:
        Tenant.objects.filter(id=tenant.id).update(payment_status="paid")
        logger.info(
            "Checkout completed for tenant=%s mode=%s",
            tenant.code, session_obj.get("mode"),
        )


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------

EVENT_DISPATCH = {
    "checkout.session.completed": lambda obj: handle_checkout_completed(obj),
    "customer.subscription.created": lambda obj: handle_subscription_event(
        "customer.subscription.created", obj
    ),
    "customer.subscription.updated": lambda obj: handle_subscription_event(
        "customer.subscription.updated", obj
    ),
    "customer.subscription.deleted": lambda obj: handle_subscription_event(
        "customer.subscription.deleted", obj
    ),
    "invoice.paid": lambda obj: handle_invoice_event("invoice.paid", obj),
    "invoice.finalized": lambda obj: handle_invoice_event("invoice.finalized", obj),
    "invoice.payment_failed": lambda obj: handle_invoice_event(
        "invoice.payment_failed", obj
    ),
    "payment_intent.succeeded": lambda obj: handle_payment_intent_event(
        "payment_intent.succeeded", obj
    ),
    "payment_intent.payment_failed": lambda obj: handle_payment_intent_event(
        "payment_intent.payment_failed", obj
    ),
    "payment_intent.canceled": lambda obj: handle_payment_intent_event(
        "payment_intent.canceled", obj
    ),
}


def process_event(event: dict) -> None:
    """Idempotent processing of a verified Stripe event.

    Stores the event in `WebhookEvent` and skips re-processing on duplicate.
    """
    event_id = event.get("id")
    event_type = event.get("type", "")
    if not event_id:
        logger.warning("Webhook event without id, ignoring")
        return

    record, created = WebhookEvent.objects.get_or_create(
        stripe_event_id=event_id,
        defaults={
            "type": event_type,
            "livemode": bool(event.get("livemode")),
            "payload": event,
        },
    )
    if not created and record.processed:
        logger.info("Duplicate Stripe event ignored: %s (%s)", event_id, event_type)
        return

    handler = EVENT_DISPATCH.get(event_type)
    if not handler:
        logger.debug("No handler for Stripe event type: %s", event_type)
        record.processed = True
        record.processed_at = timezone.now()
        record.save(update_fields=["processed", "processed_at"])
        return

    try:
        obj = (event.get("data") or {}).get("object") or {}
        handler(obj)
        record.processed = True
        record.processing_error = ""
        record.processed_at = timezone.now()
        record.save(update_fields=["processed", "processing_error", "processed_at"])
    except Exception as exc:  # pragma: no cover — webhooks must never 5xx Stripe loop
        logger.exception("Failed to process Stripe webhook %s (%s)", event_id, event_type)
        record.processing_error = f"{type(exc).__name__}: {exc}"
        record.save(update_fields=["processing_error"])
        raise
