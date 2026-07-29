"""Endpoints du pointage mobile : invitations publiques + CRUD des sites."""
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from audit.mixins import AuditLogMixin, record_audit
from presence.models import Site
from presence.serializers import SiteSerializer
from presence.services import InvitationError, accept_mobile_invitation, get_invitation_by_secret
from tenants.models import TenantMembership, TenantRole
from tenants.services import has_tenant_role, scope_queryset_to_user_tenants
from tenants.serializers import AuthUserSerializer


class InvitationAcceptThrottle(ScopedRateThrottle):
    scope = "invitation_accept"


def _invitation_error_response(exc: InvitationError) -> Response:
    return Response({"code": exc.code, "detail": exc.detail}, status=exc.http_status)


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([InvitationAcceptThrottle])
def mobile_invitation_preview_api(request):
    try:
        invitation = get_invitation_by_secret(request.query_params.get("token"))
    except InvitationError as exc:
        return _invitation_error_response(exc)
    return Response(
        {
            "employee_name": invitation.employee.name,
            "tenant_name": invitation.tenant.name,
            "email": invitation.email,
            "status": invitation.status,
            "expires_at": invitation.expires_at,
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([InvitationAcceptThrottle])
def mobile_invitation_accept_api(request):
    secret = str(request.data.get("token") or "").strip()
    password = str(request.data.get("password") or "")
    if not secret or not password:
        return Response(
            {"code": "MISSING_FIELDS", "detail": "token et password sont requis."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        invitation, user = accept_mobile_invitation(secret=secret, password=password)
    except InvitationError as exc:
        return _invitation_error_response(exc)

    record_audit(
        request,
        "mobile_invitation_accepted",
        invitation.employee,
        actor=user,
        tenant_code=invitation.tenant.code,
    )

    # Auto-login : même forme que /api/auth/login/ (attendue par l'app mobile).
    refresh = RefreshToken.for_user(user)
    memberships = (
        TenantMembership.objects.select_related("tenant").filter(user=user).order_by("tenant_id")
    )
    return Response(
        {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": AuthUserSerializer(user).data,
            "tenants": [
                {
                    "id": membership.tenant_id,
                    "code": membership.tenant.code,
                    "name": membership.tenant.name,
                    "role": membership.role,
                }
                for membership in memberships
            ],
        },
        status=status.HTTP_201_CREATED,
    )


class SiteViewSet(AuditLogMixin, viewsets.ModelViewSet):
    """CRUD des sites de pointage. Lecture : membres admin du tenant ;
    écritures : rôle ≥ org_admin."""

    queryset = Site.objects.select_related("tenant").order_by("name")
    serializer_class = SiteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = scope_queryset_to_user_tenants(super().get_queryset(), self.request.user)
        tenant_code = str(self.request.query_params.get("tenant") or "").strip()
        if tenant_code:
            queryset = queryset.filter(tenant__code__iexact=tenant_code)
        return queryset

    def _require_org_admin(self, tenant):
        if not has_tenant_role(self.request.user, tenant, TenantRole.ORG_ADMIN):
            raise PermissionDenied("Rôle org_admin minimum requis pour gérer les sites.")

    def perform_create(self, serializer):
        self._require_org_admin(serializer.validated_data.get("tenant"))
        super().perform_create(serializer)

    def perform_update(self, serializer):
        instance = serializer.instance
        tenant = serializer.validated_data.get("tenant", instance.tenant)
        self._require_org_admin(tenant)
        if serializer.validated_data.get("tenant") is not None and tenant.id != instance.tenant_id:
            raise PermissionDenied("Changing tenant is not allowed for this resource.")
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self._require_org_admin(instance.tenant)
        super().perform_destroy(instance)


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def punch_notification_settings_api(request):
    """Réglages des rappels de pointage du tenant (lecture/écriture tenant_admin)."""
    from presence.notifications import get_tenant_notification_settings
    from tenants.services import resolve_tenant

    tenant_code = str(
        request.query_params.get("tenant") or request.headers.get("X-Tenant-Code") or ""
    ).strip()
    if not tenant_code:
        return Response(
            {"code": "TENANT_REQUIRED", "detail": "Le paramètre tenant est requis."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    tenant = resolve_tenant(tenant_code)
    if tenant is None:
        return Response({"detail": "Tenant inconnu."}, status=status.HTTP_404_NOT_FOUND)
    if not has_tenant_role(request.user, tenant, TenantRole.TENANT_ADMIN):
        return Response(
            {"detail": "Rôle tenant_admin requis."}, status=status.HTTP_403_FORBIDDEN
        )

    obj = get_tenant_notification_settings(tenant)
    fields = [
        "reminders_enabled",
        "warning_enabled",
        "late_enabled",
        "push_enabled",
        "email_enabled",
        "sms_enabled",
    ]
    if request.method == "PUT":
        for field in fields:
            if field in request.data:
                setattr(obj, field, bool(request.data[field]))
        obj.save()
        record_audit(request, "update_punch_notification_settings", tenant, tenant_code=tenant.code)
    return Response({field: getattr(obj, field) for field in fields})
