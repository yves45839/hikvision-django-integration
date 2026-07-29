"""Dispatch multi-canal des rappels de pointage.

Trois canaux indépendants (un échec n'empêche jamais les autres) :
- push Expo (HTTPS direct, gratuit),
- email (infrastructure SMTP existante),
- SMS (backend pluggable, Noop par défaut).
Chaque canal produit un statut sent/failed/skipped persisté sur le
PunchReminderLog.
"""
from __future__ import annotations

import logging

import requests
from django.conf import settings

from presence.models import EmployeePushToken, PunchReminderLog, TenantNotificationSettings
from presence.sms import get_sms_backend
from tenants.emails import send_branded_email

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

MESSAGES = {
    "pre_start_warning": {
        "fr": {
            "title": "Pointage dans 15 minutes",
            "body": lambda ctx: f"Votre service commence à {ctx['expected_time']}. Pensez à pointer votre arrivée.",
        },
        "en": {
            "title": "Clock-in in 15 minutes",
            "body": lambda ctx: f"Your shift starts at {ctx['expected_time']}. Remember to clock in.",
        },
    },
    "late_reminder": {
        "fr": {
            "title": "Pointage d'arrivée manquant",
            "body": lambda ctx: f"Votre service a commencé à {ctx['expected_time']} et aucun pointage n'est enregistré.",
        },
        "en": {
            "title": "Missing clock-in",
            "body": lambda ctx: f"Your shift started at {ctx['expected_time']} and no clock-in has been recorded.",
        },
    },
}

EMAIL_TEMPLATES = {
    "pre_start_warning": "punch_warning",
    "late_reminder": "punch_late",
}


def get_tenant_notification_settings(tenant) -> TenantNotificationSettings:
    obj, _ = TenantNotificationSettings.objects.get_or_create(tenant=tenant)
    return obj


def _resolve_locale(tokens: list[EmployeePushToken]) -> str:
    for token in tokens:
        raw = (token.locale or "").strip().lower()
        if raw.startswith("fr"):
            return "fr"
        if raw.startswith("en"):
            return "en"
    lang = str(getattr(settings, "LANGUAGE_CODE", "fr")).lower()
    return "en" if lang.startswith("en") else "fr"


def _send_expo_push(tokens: list[EmployeePushToken], title: str, body: str, kind: str) -> str:
    active = [t for t in tokens if t.is_active]
    if not active:
        return PunchReminderLog.CHANNEL_SKIPPED
    messages = [
        {"to": t.token, "title": title, "body": body, "sound": "default", "data": {"kind": kind}}
        for t in active
    ]
    try:
        response = requests.post(
            getattr(settings, "EXPO_PUSH_URL", EXPO_PUSH_URL), json=messages, timeout=10
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        logger.exception("Envoi push Expo échoué")
        return PunchReminderLog.CHANNEL_FAILED
    tickets = payload.get("data", []) if isinstance(payload, dict) else []
    for token, ticket in zip(active, tickets):
        details = ticket.get("details") if isinstance(ticket, dict) else None
        if isinstance(details, dict) and details.get("error") == "DeviceNotRegistered":
            token.is_active = False
            token.save(update_fields=["is_active", "last_seen_at"])
    return PunchReminderLog.CHANNEL_SENT


def _send_email(employee, kind: str, context: dict, lang: str) -> str:
    to_email = (employee.email or "").strip() or (
        employee.user.email if employee.user_id else ""
    )
    if not to_email:
        return PunchReminderLog.CHANNEL_SKIPPED
    sent = send_branded_email(
        to_email=to_email,
        template_name=EMAIL_TEMPLATES[kind],
        context=context,
        lang=lang,
        fail_silently=True,
    )
    return PunchReminderLog.CHANNEL_SENT if sent else PunchReminderLog.CHANNEL_FAILED


def _send_sms(employee, body: str) -> str:
    phone = (employee.phone or "").strip()
    if not phone:
        return PunchReminderLog.CHANNEL_SKIPPED
    try:
        sent = get_sms_backend().send(phone=phone, message=body)
    except Exception:
        logger.exception("Envoi SMS échoué")
        return PunchReminderLog.CHANNEL_FAILED
    return PunchReminderLog.CHANNEL_SENT if sent else PunchReminderLog.CHANNEL_SKIPPED


def dispatch_punch_reminder(reminder: PunchReminderLog) -> None:
    """Envoie le rappel sur les canaux activés par le tenant et persiste les
    statuts par canal. Chaque canal est isolé : un échec n'affecte pas les
    autres."""
    employee = reminder.employee
    notif_settings = get_tenant_notification_settings(employee.tenant)
    tokens = list(employee.push_tokens.filter(is_active=True))
    lang = _resolve_locale(tokens)
    if reminder.expected_start_at is not None:
        from employees.schedule_resolver import ScheduleResolver

        tz = ScheduleResolver().resolve_employee_timezone(employee)
        expected_local = reminder.expected_start_at.astimezone(tz).strftime("%H:%M")
    else:
        expected_local = "--:--"
    strings = MESSAGES[reminder.kind][lang]
    context = {
        "employee_name": employee.name,
        "tenant_name": employee.tenant.name,
        "expected_time": expected_local,
        "date": reminder.date,
    }
    title = strings["title"]
    body = strings["body"](context)
    errors: dict = {}

    if notif_settings.push_enabled:
        try:
            reminder.push_status = _send_expo_push(tokens, title, body, reminder.kind)
        except Exception as exc:  # pragma: no cover - double sécurité
            reminder.push_status = PunchReminderLog.CHANNEL_FAILED
            errors["push"] = str(exc)
    if notif_settings.email_enabled:
        try:
            reminder.email_status = _send_email(employee, reminder.kind, context, lang)
        except Exception as exc:  # pragma: no cover
            reminder.email_status = PunchReminderLog.CHANNEL_FAILED
            errors["email"] = str(exc)
    if notif_settings.sms_enabled:
        try:
            reminder.sms_status = _send_sms(employee, f"{title} — {body}")
        except Exception as exc:  # pragma: no cover
            reminder.sms_status = PunchReminderLog.CHANNEL_FAILED
            errors["sms"] = str(exc)

    reminder.errors = errors
    reminder.save(update_fields=["push_status", "email_status", "sms_status", "errors"])
