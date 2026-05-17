"""Billing service layer — wraps the Stripe SDK so the rest of the app
never has to import `stripe` directly.

The functions here are pure / testable: they take Django objects in,
talk to Stripe, and return Stripe responses (dicts). They never write to
the database — that's the responsibility of the webhook handler and the
view layer.
"""
from .stripe_client import get_stripe
from .checkout import (
    create_checkout_session_subscription,
    create_checkout_session_one_time,
    create_billing_portal_session,
)
from .customers import get_or_create_customer
from .payments import create_payment_intent
from .usage import report_usage

__all__ = [
    "get_stripe",
    "create_checkout_session_subscription",
    "create_checkout_session_one_time",
    "create_billing_portal_session",
    "get_or_create_customer",
    "create_payment_intent",
    "report_usage",
]
