import logging

from audit.utils import audit_log

logger = logging.getLogger(__name__)


def _resolve_tenant_code(obj) -> str:
    tenant = getattr(obj, "tenant", None)
    if tenant is not None:
        return str(getattr(tenant, "code", "") or "")
    return str(getattr(obj, "tenant_code", "") or "")


def record_audit(request, action: str, target_obj=None, tenant_code: str = "", actor=None, **extra) -> None:
    """Best-effort audit write: a failing audit insert must never break the mutation."""
    try:
        if actor is None:
            actor = getattr(request, "user", None)
        if actor is not None and not actor.is_authenticated:
            actor = None
        if not tenant_code and target_obj is not None:
            tenant_code = _resolve_tenant_code(target_obj)
        audit_log(
            actor=actor,
            action=action,
            target_obj=target_obj,
            request=request,
            tenant_code=tenant_code,
            **extra,
        )
    except Exception:
        logger.exception("audit_log failed for action %s", action)


class AuditLogMixin:
    """Writes an AuditEvent on create/update/destroy of a ModelViewSet."""

    def perform_create(self, serializer):
        super().perform_create(serializer)
        obj = serializer.instance
        record_audit(self.request, f"create_{obj.__class__.__name__.lower()}", obj)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        obj = serializer.instance
        record_audit(self.request, f"update_{obj.__class__.__name__.lower()}", obj)

    def perform_destroy(self, instance):
        action = f"delete_{instance.__class__.__name__.lower()}"
        tenant_code = _resolve_tenant_code(instance)
        target_id = str(instance.pk)
        target_model = instance.__class__.__name__
        super().perform_destroy(instance)
        record_audit(
            self.request,
            action,
            None,
            tenant_code=tenant_code,
            target_model=target_model,
            target_id=target_id,
        )
