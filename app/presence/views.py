"""Endpoints publics d'invitation mobile (preview + acceptation)."""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from audit.mixins import record_audit
from presence.services import InvitationError, accept_mobile_invitation, get_invitation_by_secret
from tenants.models import TenantMembership
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
