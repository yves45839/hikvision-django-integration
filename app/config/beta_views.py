"""Endpoint public exposant le statut Beta au frontend.

Lu par le frontend pour :
- afficher la bannière "Beta gratuite"
- masquer les pages pricing / abonnement
- ouvrir le signup public

GET /api/beta/info/
    -> { "beta_mode": true, "billing_enabled": false, "stripe_configured": false }
"""
from __future__ import annotations

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def beta_info(_request):
    stripe_configured = bool(
        getattr(settings, "STRIPE_SECRET_KEY", "")
        and getattr(settings, "STRIPE_PUBLISHABLE_KEY", "")
    )
    beta_mode = bool(getattr(settings, "BETA_MODE", False))
    return Response(
        {
            "beta_mode": beta_mode,
            "billing_enabled": (not beta_mode) and stripe_configured,
            "stripe_configured": stripe_configured,
            "signup_open": True,  # beta publique
            "banner_message_fr": (
                "Beta gratuite — vous utilisez actuellement la version preview de LR Time."
                if beta_mode
                else ""
            ),
            "banner_message_en": (
                "Free beta — you are currently using the LR Time preview."
                if beta_mode
                else ""
            ),
        }
    )
