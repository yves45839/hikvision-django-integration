"""Sentry middleware for Phase 7 — Observabilité (7.1)."""

import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class SentryContextMiddleware:
    """Injecte tenant_id, org_id, user_id dans le scope Sentry pour chaque requête."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._sentry_available = bool(getattr(settings, "SENTRY_DSN", ""))

    def __call__(self, request):
        if self._sentry_available:
            try:
                import sentry_sdk

                with sentry_sdk.configure_scope() as scope:
                    if request.user.is_authenticated:
                        scope.set_user({"id": request.user.id, "email": request.user.email})
                        scope.set_tag("user_id", str(request.user.id))
                        # Résoudre tenant depuis la membership primaire
                        try:
                            from tenants.models import TenantUser
                            tenant_user = (
                                TenantUser.objects
                                .select_related("tenant")
                                .filter(user=request.user)
                                .first()
                            )
                            if tenant_user:
                                scope.set_tag("tenant_id", str(tenant_user.tenant.id))
                                scope.set_tag("tenant_code", tenant_user.tenant.tenant_code)
                        except Exception:
                            pass  # Tenant not found or model doesn't exist yet
                    scope.set_tag("release", getattr(settings, "SENTRY_RELEASE", "dev"))
            except Exception:
                pass  # Ne jamais laisser Sentry crasher l'app
        return self.get_response(request)
