from datetime import datetime, time

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from audit.models import AuditEvent
from audit.serializers import AuditEventSerializer
from tenants.models import TenantRole
from tenants.services import has_tenant_role, resolve_tenant

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def _is_admin_request(request) -> bool:
    user = request.user
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


def _parse_date(value: str):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def audit_events_api(request):
    tenant_code = str(request.query_params.get("tenant") or "").strip()

    if not _is_admin_request(request):
        if not tenant_code:
            return Response(
                {"detail": "Le paramètre tenant est requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tenant = resolve_tenant(tenant_code)
        if tenant is None:
            return Response({"detail": "Tenant inconnu."}, status=status.HTTP_404_NOT_FOUND)
        if not has_tenant_role(request.user, tenant, TenantRole.OPERATOR):
            return Response(
                {"detail": "Portée tenant insuffisante pour consulter l'audit."},
                status=status.HTTP_403_FORBIDDEN,
            )

    queryset = AuditEvent.objects.select_related("actor").order_by("-created_at", "-id")
    if tenant_code:
        queryset = queryset.filter(tenant_code__iexact=tenant_code)

    actor = str(request.query_params.get("actor") or "").strip()
    if actor:
        queryset = queryset.filter(actor__username__icontains=actor)

    action = str(request.query_params.get("action") or "").strip()
    if action:
        queryset = queryset.filter(action__icontains=action)

    target_model = str(request.query_params.get("target_model") or "").strip()
    if target_model:
        queryset = queryset.filter(target_model__iexact=target_model)

    date_from = _parse_date(request.query_params.get("date_from"))
    if date_from:
        queryset = queryset.filter(
            created_at__gte=timezone.make_aware(datetime.combine(date_from, time.min))
        )

    date_to = _parse_date(request.query_params.get("date_to"))
    if date_to:
        queryset = queryset.filter(
            created_at__lte=timezone.make_aware(datetime.combine(date_to, time.max))
        )

    before_id = str(request.query_params.get("before_id") or "").strip()
    if before_id.isdigit():
        queryset = queryset.filter(id__lt=int(before_id))

    try:
        limit = int(request.query_params.get("limit") or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    limit = max(1, min(limit, MAX_LIMIT))

    rows = list(queryset[:limit])
    return Response(
        {
            "count": len(rows),
            "results": AuditEventSerializer(rows, many=True).data,
        }
    )
