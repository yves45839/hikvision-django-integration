"""Singleton-ish Stripe SDK initializer.

We import `stripe` lazily so that the rest of the codebase (tests, migrations,
management commands that don't touch billing) doesn't require the SDK to be
installed or the API key to be configured.
"""
from __future__ import annotations

from django.conf import settings


def get_stripe():
    """Return a configured `stripe` module.

    Raises ImproperlyConfigured if STRIPE_SECRET_KEY is missing.
    """
    import stripe  # local import — only mandatory if billing is actually used
    from django.core.exceptions import ImproperlyConfigured

    secret_key = getattr(settings, "STRIPE_SECRET_KEY", "")
    if not secret_key:
        raise ImproperlyConfigured(
            "STRIPE_SECRET_KEY is not configured. "
            "Set it in your environment / .env file."
        )

    stripe.api_key = secret_key
    api_version = getattr(settings, "STRIPE_API_VERSION", "")
    if api_version:
        stripe.api_version = api_version
    return stripe
