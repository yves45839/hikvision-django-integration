"""Backends SMS pluggables.

Le SMS n'est jamais gratuit à grande échelle : le canal est désactivé par
défaut (NoopSmsBackend). Pour l'activer, configurer ``SMS_BACKEND`` vers un
backend réel (ex. TwilioSmsBackend) et fournir ses identifiants.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


class BaseSmsBackend:
    def send(self, *, phone: str, message: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class NoopSmsBackend(BaseSmsBackend):
    """Backend par défaut : journalise sans envoyer (canal gratuit inexistant)."""

    def send(self, *, phone: str, message: str) -> bool:
        logger.info("SMS (noop) vers %s: %s", phone, message[:80])
        return False


class TwilioSmsBackend(BaseSmsBackend):
    """Gabarit d'intégration Twilio (payant) — nécessite le paquet ``twilio``
    et TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER."""

    def __init__(self):
        sid = getattr(settings, "TWILIO_ACCOUNT_SID", "")
        token = getattr(settings, "TWILIO_AUTH_TOKEN", "")
        self.from_number = getattr(settings, "TWILIO_FROM_NUMBER", "")
        if not (sid and token and self.from_number):
            raise ImproperlyConfigured(
                "TwilioSmsBackend requiert TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN "
                "et TWILIO_FROM_NUMBER."
            )
        try:
            from twilio.rest import Client  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise ImproperlyConfigured("Le paquet 'twilio' n'est pas installé.") from exc
        self._client = Client(sid, token)

    def send(self, *, phone: str, message: str) -> bool:  # pragma: no cover - réseau
        self._client.messages.create(to=phone, from_=self.from_number, body=message)
        return True


def get_sms_backend() -> BaseSmsBackend:
    path = getattr(settings, "SMS_BACKEND", "presence.sms.NoopSmsBackend")
    return import_string(path)()
