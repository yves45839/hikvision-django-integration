"""
Email rendering & sending helpers for transactional emails.

All outgoing transactional emails (password reset, payment confirmation,
payment failure, etc.) go through this module so they share the same
LR Time visual identity and Label Retail signature.

Templates live in ``tenants/templates/emails/<lang>/<name>.html`` and ``.txt``.
The base layout is ``tenants/templates/emails/base.html`` (and ``base.txt``).
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import translation

logger = logging.getLogger(__name__)


SUPPORTED_LANGS = ("fr", "en")
DEFAULT_LANG = "fr"


def _resolve_from_email() -> str:
    """Pick the best From address from settings, falling back to a sane default."""
    host_user = str(getattr(settings, "EMAIL_HOST_USER", "") or "").strip()
    if host_user and "@" in host_user:
        return host_user
    configured = str(getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
    if configured and "@" in configured:
        return configured
    return "no-reply@label-ci.com"


def _normalize_lang(lang: Optional[str]) -> str:
    candidate = str(lang or "").strip().lower()[:2]
    if candidate in SUPPORTED_LANGS:
        return candidate
    # Fall back to project default if it's supported, otherwise FR.
    project_default = str(getattr(settings, "LANGUAGE_CODE", "") or "")[:2].lower()
    if project_default in SUPPORTED_LANGS:
        return project_default
    return DEFAULT_LANG


def render_branded_email(
    *,
    template_name: str,
    context: Mapping[str, Any],
    lang: Optional[str] = None,
) -> tuple[str, str, str]:
    """Render a branded transactional email.

    Args:
        template_name: e.g. ``"password_reset"``. Resolves to
            ``emails/<lang>/<template_name>.html`` and ``.txt``.
        context: Template context. The keys ``lang`` and ``brand_name``
            are added automatically if missing.
        lang: ``"fr"`` or ``"en"`` (case-insensitive). Falls back to
            ``settings.LANGUAGE_CODE`` then ``"fr"``.

    Returns:
        ``(subject, html_body, text_body)``.
    """
    resolved_lang = _normalize_lang(lang)
    base_ctx: dict[str, Any] = {
        "lang": resolved_lang,
        "brand_name": "Label Retail",
    }
    base_ctx.update(dict(context))

    html_path = f"emails/{resolved_lang}/{template_name}.html"
    text_path = f"emails/{resolved_lang}/{template_name}.txt"

    # Activate the right locale so Django's date/time filters localize correctly.
    with translation.override(resolved_lang):
        html_body = render_to_string(html_path, base_ctx)
        text_body = render_to_string(text_path, base_ctx)

    # Subject is rendered by extracting the {% block subject %} from the HTML.
    # Simpler: derive it from a sibling subject template if present, else
    # fall back to the {% block subject %} content the base.html exposes.
    subject = _extract_subject(html_body) or "Label Retail"
    return subject, html_body, text_body


def _extract_subject(html_body: str) -> str:
    """Pull the <title>...</title> contents from a rendered HTML email.

    Our base.html sets <title>{% block subject %}...{% endblock %}</title>,
    so the rendered <title> is the email subject.
    """
    start_tag = "<title>"
    end_tag = "</title>"
    start = html_body.find(start_tag)
    if start == -1:
        return ""
    start += len(start_tag)
    end = html_body.find(end_tag, start)
    if end == -1:
        return ""
    return html_body[start:end].strip()


def send_branded_email(
    *,
    to_email: str,
    template_name: str,
    context: Mapping[str, Any],
    lang: Optional[str] = None,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    fail_silently: bool = False,
) -> bool:
    """Render and send a branded transactional email.

    Returns True on success. Raises (or returns False if ``fail_silently``)
    on SMTP/connection errors. Template rendering errors always bubble up.
    """
    if not to_email or "@" not in str(to_email or ""):
        raise ValueError("send_branded_email: a valid recipient email is required.")

    subject, html_body, text_body = render_branded_email(
        template_name=template_name,
        context=context,
        lang=lang,
    )

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=_resolve_from_email(),
        to=[to_email],
        cc=cc or None,
        bcc=bcc or None,
    )
    message.attach_alternative(html_body, "text/html")
    # Mark plain-text part as text/plain; charset already utf-8 by default.
    try:
        sent = message.send(fail_silently=fail_silently)
        return bool(sent)
    except Exception:  # pragma: no cover — caller decides what to do.
        logger.exception(
            "Failed to send branded email template=%s to=%s",
            template_name,
            to_email,
        )
        if fail_silently:
            return False
        raise


# ---------------------------------------------------------------------------
# Convenience wrappers — the names mirror the transactional events so that
# callers don't have to remember template_name strings.
# ---------------------------------------------------------------------------


def send_password_reset_email(
    *,
    to_email: str,
    otp_code: str,
    reset_link: str,
    expires_at,
    first_name: str = "",
    user_email: str = "",
    lang: Optional[str] = None,
) -> bool:
    return send_branded_email(
        to_email=to_email,
        template_name="password_reset",
        context={
            "otp_code": otp_code,
            "reset_link": reset_link,
            "expires_at": expires_at,
            "first_name": first_name,
            "user_email": user_email or to_email,
        },
        lang=lang,
    )


def send_payment_success_email(
    *,
    to_email: str,
    first_name: str = "",
    tenant_name: str = "",
    plan_name: str = "",
    amount: str = "",
    currency: str = "EUR",
    invoice_number: str = "",
    invoice_url: str = "",
    invoice_pdf: str = "",
    paid_at=None,
    period_start=None,
    period_end=None,
    lang: Optional[str] = None,
) -> bool:
    return send_branded_email(
        to_email=to_email,
        template_name="payment_success",
        context={
            "first_name": first_name,
            "tenant_name": tenant_name,
            "plan_name": plan_name,
            "amount": amount,
            "currency": currency,
            "invoice_number": invoice_number,
            "invoice_url": invoice_url,
            "invoice_pdf": invoice_pdf,
            "paid_at": paid_at,
            "period_start": period_start,
            "period_end": period_end,
        },
        lang=lang,
    )


def send_payment_failed_email(
    *,
    to_email: str,
    first_name: str = "",
    tenant_name: str = "",
    amount: str = "",
    currency: str = "EUR",
    invoice_number: str = "",
    failure_reason: str = "",
    retry_url: str = "",
    attempted_at=None,
    lang: Optional[str] = None,
) -> bool:
    return send_branded_email(
        to_email=to_email,
        template_name="payment_failed",
        context={
            "first_name": first_name,
            "tenant_name": tenant_name,
            "amount": amount,
            "currency": currency,
            "invoice_number": invoice_number,
            "failure_reason": failure_reason,
            "retry_url": retry_url,
            "attempted_at": attempted_at,
        },
        lang=lang,
    )
