from __future__ import annotations

import logging
import secrets
import uuid

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, logout as django_logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from employees.models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    OrganizationRole,
)
from tenants.models import (
    EmailVerificationToken,
    OrganizationCustomRole,
    OrganizationCustomRoleAssignment,
    PasswordResetToken,
    PaymentStatus,
    Tenant,
    TenantMembership,
    TenantRole,
)
from tenants.serializers import (
    AuthUserSerializer,
    ChangePasswordSerializer,
    OrganizationCustomRoleSerializer,
    OrganizationUserCreateSerializer,
)
from tenants.services import ROLE_RANK, has_organization_role, resolve_tenant
from tenants.emails import send_password_reset_email


def _request_lang(request) -> str:
    """Pick FR or EN from the request, falling back to the project default."""
    accept = str(request.META.get("HTTP_ACCEPT_LANGUAGE", "") or "").lower()
    if accept.startswith("en"):
        return "en"
    if accept.startswith("fr"):
        return "fr"
    explicit = str(request.data.get("lang") or request.data.get("language") or "").lower()
    if explicit.startswith("en"):
        return "en"
    if explicit.startswith("fr"):
        return "fr"
    default = str(getattr(settings, "LANGUAGE_CODE", "fr") or "fr")[:2].lower()
    return "en" if default == "en" else "fr"


User = get_user_model()
logger = logging.getLogger(__name__)


def _email_domain(email: str) -> str:
    return str(email or "").strip().split("@")[-1].lower() if "@" in str(email or "") else ""


def _unique_tenant_code(seed: str) -> str:
    base = slugify(seed or "")[:40] or "tenant"
    candidate = base
    index = 1
    while Tenant.objects.filter(code__iexact=candidate).exists():
        index += 1
        candidate = f"{base}-{index}"[:50]
    return candidate


def _unique_org_code(tenant: Tenant, seed: str) -> str:
    base = slugify(seed or "")[:48] or "org-default"
    candidate = base
    index = 1
    while Organization.objects.filter(tenant=tenant, code__iexact=candidate).exists():
        index += 1
        candidate = f"{base}-{index}"[:64]
    return candidate


def _unique_username(seed: str) -> str:
    base = slugify(seed or "")[:120] or "user"
    candidate = base
    index = 1
    while User.objects.filter(username__iexact=candidate).exists():
        index += 1
        candidate = f"{base}-{index}"[:150]
    return candidate


def _auto_activate_tenant(tenant: Tenant) -> bool:
    has_active_tenant_admin = TenantMembership.objects.filter(
        tenant=tenant,
        role=TenantRole.TENANT_ADMIN,
        user__is_active=True,
    ).exists()
    payment_ok = tenant.payment_status in {PaymentStatus.NOT_REQUIRED, PaymentStatus.PAID}
    domain_ok = tenant.is_domain_verified
    tenant.is_active = bool(has_active_tenant_admin and payment_ok and domain_ok)
    tenant.requires_manual_review = not tenant.is_active
    tenant.save(update_fields=["is_active", "requires_manual_review"])
    return tenant.is_active


def _can_manage_org_members(user, organization: Organization) -> bool:
    return has_organization_role(user, organization, allowed_org_roles=(OrganizationRole.ORG_ADMIN,))


def _frontend_token_link(path: str, token: str) -> str:
    base_url = str(getattr(settings, "FRONTEND_AUTH_BASE_URL", "") or "").strip().rstrip("/")
    if not base_url:
        return ""
    path_value = f"/{str(path or '').strip().lstrip('/')}"
    return f"{base_url}{path_value}?token={token}"


def _generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _resolve_from_email() -> str:
    host_user = str(getattr(settings, "EMAIL_HOST_USER", "") or "").strip()
    if host_user and "@" in host_user:
        return host_user
    configured = str(getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
    if configured and "@" in configured:
        return configured
    return "no-reply@label-ci.com"


def _send_auth_email(*, to_email: str, subject: str, body: str) -> None:
    send_mail(
        subject=subject,
        message=body,
        from_email=_resolve_from_email(),
        recipient_list=[to_email],
        fail_silently=False,
    )


def _build_verification_body(*, tenant_name: str, token: uuid.UUID, otp_code: str, expires_at) -> str:
    verify_link = _frontend_token_link("auth/verify-email", str(token))
    return (
        f"Bonjour,\n\n"
        f"Votre compte pour le tenant '{tenant_name}' a ete cree.\n"
        f"Code OTP: {otp_code}\n"
        f"Token de verification: {token}\n"
        f"Lien de verification: {verify_link or 'N/A'}\n\n"
        f"Ce code/token expire le {expires_at}.\n"
        f"Si vous n'etes pas a l'origine de cette demande, ignorez cet email.\n"
    )


def _build_password_reset_body(*, token: uuid.UUID, otp_code: str, expires_at) -> str:
    reset_link = _frontend_token_link("auth/reset-password", str(token))
    return (
        f"Bonjour,\n\n"
        f"Une demande de reinitialisation de mot de passe a ete initiee.\n"
        f"Code OTP: {otp_code}\n"
        f"Token de reinitialisation: {token}\n"
        f"Lien de reinitialisation: {reset_link or 'N/A'}\n\n"
        f"Ce code/token expire le {expires_at}.\n"
        f"Si vous n'etes pas a l'origine de cette demande, ignorez cet email.\n"
    )


def _mark_verification_as_expired(verification: EmailVerificationToken) -> None:
    verification.is_used = True
    verification.used_at = verification.expires_at
    verification.save(update_fields=["is_used", "used_at"])


def _mark_password_reset_as_expired(reset_token: PasswordResetToken) -> None:
    reset_token.is_used = True
    reset_token.used_at = reset_token.expires_at
    reset_token.save(update_fields=["is_used", "used_at"])


@api_view(["POST"])
@permission_classes([AllowAny])
def client_signup_api(request):
    email = str(request.data.get("email") or "").strip().lower()
    password = str(request.data.get("password") or "")
    tenant_name = str(request.data.get("tenant_name") or "").strip()
    tenant_code = str(request.data.get("tenant_code") or "").strip()
    organization_name = str(request.data.get("organization_name") or "Default Organization").strip()
    requested_domain = str(request.data.get("domain") or "").strip().lower()
    require_payment = str(request.data.get("require_payment", "false")).strip().lower() in {"1", "true", "yes", "on"}

    if not email or "@" not in email:
        return Response({"detail": "Valid email is required."}, status=status.HTTP_400_BAD_REQUEST)
    if len(password) < 8:
        return Response({"detail": "Password must be at least 8 characters."}, status=status.HTTP_400_BAD_REQUEST)
    if not tenant_name:
        return Response({"detail": "tenant_name is required."}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
        return Response({"detail": "A user with this email already exists."}, status=status.HTTP_409_CONFLICT)

    try:
        with transaction.atomic():
            username = _unique_username(email)
            user = User.objects.create_user(username=username, email=email, password=password, is_active=False)

            tenant = Tenant.objects.create(
                name=tenant_name,
                code=tenant_code or _unique_tenant_code(tenant_name),
                domain=requested_domain or _email_domain(email),
                is_domain_verified=False,
                is_active=False,
                payment_status=PaymentStatus.PENDING if require_payment else PaymentStatus.NOT_REQUIRED,
                requires_manual_review=True,
            )

            organization = Organization.objects.create(
                tenant=tenant,
                name=organization_name,
                code=_unique_org_code(tenant, organization_name),
            )

            TenantMembership.objects.create(
                user=user,
                tenant=tenant,
                role=TenantRole.TENANT_ADMIN,
                is_primary=True,
            )
            OrganizationMembership.objects.create(
                user=user,
                organization=organization,
                role=OrganizationRole.ORG_ADMIN,
            )

            verification = EmailVerificationToken.objects.create(
                user=user,
                tenant=tenant,
                otp_code=_generate_otp_code(),
            )
    except Exception as exc:
        logger.exception("Failed to complete signup transaction email=%s", email)
        return Response(
            {"detail": f"Unable to complete signup: {exc}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    verification_body = _build_verification_body(
        tenant_name=tenant.name,
        token=verification.token,
        otp_code=verification.otp_code,
        expires_at=verification.expires_at,
    )
    email_sent = False
    try:
        _send_auth_email(
            to_email=user.email,
            subject="Verification de votre compte Label CI",
            body=verification_body,
        )
        email_sent = True
    except Exception as exc:
        logger.exception("Failed to send signup verification email email=%s", email)
        email_sent = False

    payload = {
            "status": "pending_verification",
            "tenant": {
                "id": tenant.id,
                "name": tenant.name,
                "code": tenant.code,
                "is_active": tenant.is_active,
                "payment_status": tenant.payment_status,
            },
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
            },
            "default_organization": {
                "id": organization.id,
                "name": organization.name,
                "code": organization.code,
            },
            "email_verification_expires_at": verification.expires_at,
            "email_sent": email_sent,
            "next_step": "verify_email_with_token_or_otp",
        }
    if settings.DEBUG:
        payload["email_verification_token"] = str(verification.token)
        payload["email_verification_otp"] = verification.otp_code

    return Response(
        payload,
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def verify_email_api(request):
    token_text = str(request.data.get("token") or "").strip()
    email = str(request.data.get("email") or "").strip().lower()
    otp_code = str(request.data.get("otp") or "").strip()

    verification = None
    if token_text:
        try:
            token_uuid = uuid.UUID(token_text)
        except ValueError:
            return Response({"detail": "Invalid token format."}, status=status.HTTP_400_BAD_REQUEST)
        verification = (
            EmailVerificationToken.objects.select_related("user", "tenant")
            .filter(token=token_uuid)
            .first()
        )
    elif email and otp_code:
        if len(otp_code) != 6 or not otp_code.isdigit():
            return Response({"detail": "Invalid OTP format."}, status=status.HTTP_400_BAD_REQUEST)
        verification = (
            EmailVerificationToken.objects.select_related("user", "tenant")
            .filter(user__email__iexact=email, otp_code=otp_code, is_used=False)
            .order_by("-created_at")
            .first()
        )
    else:
        return Response(
            {"detail": "Provide token, or email and otp."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if verification is None:
        return Response({"detail": "Verification not found."}, status=status.HTTP_404_NOT_FOUND)
    if verification.is_used:
        return Response({"detail": "Verification already used."}, status=status.HTTP_409_CONFLICT)
    if verification.is_expired:
        _mark_verification_as_expired(verification)
        return Response({"detail": "Verification expired."}, status=status.HTTP_410_GONE)

    with transaction.atomic():
        user = verification.user
        user.is_active = True
        user.save(update_fields=["is_active"])

        tenant = verification.tenant
        if tenant.domain and tenant.domain == _email_domain(user.email):
            tenant.is_domain_verified = True
            tenant.save(update_fields=["is_domain_verified"])

        verification.is_used = True
        verification.used_at = timezone.now()
        verification.save(update_fields=["is_used", "used_at"])

        is_active = _auto_activate_tenant(tenant)

    return Response(
        {
            "status": "verified",
            "tenant": {
                "id": tenant.id,
                "code": tenant.code,
                "is_active": is_active,
                "is_domain_verified": tenant.is_domain_verified,
                "payment_status": tenant.payment_status,
            },
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
            },
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def resend_email_verification_api(request):
    email = str(request.data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return Response({"detail": "Valid email is required."}, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
    if user.is_active:
        return Response({"detail": "User is already verified."}, status=status.HTTP_409_CONFLICT)

    membership = (
        TenantMembership.objects.select_related("tenant")
        .filter(user=user)
        .order_by("-is_primary", "id")
        .first()
    )
    if membership is None:
        return Response({"detail": "No tenant membership found for this user."}, status=status.HTTP_404_NOT_FOUND)

    now = timezone.now()
    EmailVerificationToken.objects.filter(user=user, tenant=membership.tenant, is_used=False).update(
        is_used=True,
        used_at=now,
    )
    verification = EmailVerificationToken.objects.create(
        user=user,
        tenant=membership.tenant,
        otp_code=_generate_otp_code(),
    )
    verification_body = _build_verification_body(
        tenant_name=membership.tenant.name,
        token=verification.token,
        otp_code=verification.otp_code,
        expires_at=verification.expires_at,
    )
    try:
        _send_auth_email(
            to_email=user.email,
            subject="Nouveau code de verification Label CI",
            body=verification_body,
        )
    except Exception as exc:
        logger.exception("Failed to resend verification email email=%s", email)
        return Response(
            {"detail": f"Unable to send verification email: {exc}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    payload = {
        "status": "resent",
        "email": user.email,
        "email_verification_expires_at": verification.expires_at,
        "email_sent": True,
    }
    if settings.DEBUG:
        payload["email_verification_token"] = str(verification.token)
        payload["email_verification_otp"] = verification.otp_code
    return Response(payload, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
def request_password_reset_api(request):
    identifier = str(
        request.data.get("identifier")
        or request.data.get("email")
        or request.data.get("username")
        or ""
    ).strip()
    if not identifier:
        return Response(
            {"detail": "identifier/email/username is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = None
    if "@" in identifier:
        user = User.objects.filter(email__iexact=identifier).first()
    else:
        user = User.objects.filter(username__iexact=identifier).first()

    # Avoid user enumeration: return 200 even when account does not exist or is inactive.
    if user is None or not user.is_active:
        return Response({"status": "reset_requested"}, status=status.HTTP_200_OK)

    membership = (
        TenantMembership.objects.select_related("tenant")
        .filter(user=user)
        .order_by("-is_primary", "id")
        .first()
    )
    now = timezone.now()
    PasswordResetToken.objects.filter(user=user, is_used=False).update(is_used=True, used_at=now)
    reset_token = PasswordResetToken.objects.create(
        user=user,
        tenant=membership.tenant if membership else None,
        otp_code=_generate_otp_code(),
    )

    reset_link = _frontend_token_link("auth/reset-password", str(reset_token.token))
    try:
        send_password_reset_email(
            to_email=user.email,
            otp_code=reset_token.otp_code,
            reset_link=reset_link,
            expires_at=reset_token.expires_at,
            first_name=getattr(user, "first_name", "") or "",
            user_email=user.email,
            lang=_request_lang(request),
        )
    except Exception as exc:
        logger.exception("Failed to send password reset email identifier=%s", identifier)
        return Response(
            {"detail": f"Unable to send password reset email: {exc}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    payload = {
        "status": "reset_requested",
        "email_sent": True,
        "expires_at": reset_token.expires_at,
    }
    if settings.DEBUG:
        payload["password_reset_token"] = str(reset_token.token)
        payload["password_reset_otp"] = reset_token.otp_code
    return Response(payload, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
def confirm_password_reset_api(request):
    token_text = str(request.data.get("token") or "").strip()
    email = str(request.data.get("email") or "").strip().lower()
    otp_code = str(request.data.get("otp") or "").strip()
    new_password = str(request.data.get("new_password") or "")

    if len(new_password) < 8:
        return Response(
            {"detail": "new_password must be at least 8 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    reset_token = None
    if token_text:
        try:
            token_uuid = uuid.UUID(token_text)
        except ValueError:
            return Response({"detail": "Invalid token format."}, status=status.HTTP_400_BAD_REQUEST)
        reset_token = PasswordResetToken.objects.select_related("user").filter(token=token_uuid).first()
    elif email and otp_code:
        if len(otp_code) != 6 or not otp_code.isdigit():
            return Response({"detail": "Invalid OTP format."}, status=status.HTTP_400_BAD_REQUEST)
        reset_token = (
            PasswordResetToken.objects.select_related("user")
            .filter(user__email__iexact=email, otp_code=otp_code, is_used=False)
            .order_by("-created_at")
            .first()
        )
    else:
        return Response(
            {"detail": "Provide token, or email and otp."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if reset_token is None:
        return Response({"detail": "Reset token not found."}, status=status.HTTP_404_NOT_FOUND)
    if reset_token.is_used:
        return Response({"detail": "Reset token already used."}, status=status.HTTP_409_CONFLICT)
    if reset_token.is_expired:
        _mark_password_reset_as_expired(reset_token)
        return Response({"detail": "Reset token expired."}, status=status.HTTP_410_GONE)

    user = reset_token.user
    try:
        validate_password(new_password, user=user)
    except DjangoValidationError as exc:
        return Response({"detail": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        user.set_password(new_password)
        user.save(update_fields=["password"])

        now = timezone.now()
        PasswordResetToken.objects.filter(user=user, is_used=False).exclude(id=reset_token.id).update(
            is_used=True,
            used_at=now,
        )
        reset_token.is_used = True
        reset_token.used_at = now
        reset_token.save(update_fields=["is_used", "used_at"])

    return Response({"status": "password_reset"}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
def payment_callback_api(request):
    expected_token = str(getattr(settings, "PAYMENT_WEBHOOK_TOKEN", "") or "").strip()
    provided_token = str(request.headers.get("X-PAYMENT-TOKEN") or "").strip()

    if expected_token and provided_token != expected_token:
        return Response({"detail": "Invalid payment webhook token."}, status=status.HTTP_403_FORBIDDEN)

    tenant_code = str(request.data.get("tenant_code") or "").strip()
    payment_status = str(request.data.get("payment_status") or "").strip().lower()

    tenant = resolve_tenant(tenant_code)
    if tenant is None:
        return Response({"detail": "Tenant not found."}, status=status.HTTP_404_NOT_FOUND)
    if payment_status not in {PaymentStatus.PENDING, PaymentStatus.PAID, PaymentStatus.FAILED, PaymentStatus.NOT_REQUIRED}:
        return Response({"detail": "Invalid payment_status."}, status=status.HTTP_400_BAD_REQUEST)

    tenant.payment_status = payment_status
    tenant.save(update_fields=["payment_status"])
    is_active = _auto_activate_tenant(tenant)

    return Response(
        {
            "status": "updated",
            "tenant": tenant.code,
            "payment_status": tenant.payment_status,
            "is_active": is_active,
            "requires_manual_review": tenant.requires_manual_review,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_organization_invitation_api(request, organization_id: int):
    organization = Organization.objects.select_related("tenant").filter(id=organization_id).first()
    if organization is None:
        return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)
    if not has_organization_role(request.user, organization, allowed_org_roles=(OrganizationRole.ORG_ADMIN,)):
        return Response({"detail": "Insufficient permissions to invite users."}, status=status.HTTP_403_FORBIDDEN)

    email = str(request.data.get("email") or "").strip().lower()
    role = str(request.data.get("role") or "").strip().lower()
    if not email or "@" not in email:
        return Response({"detail": "Valid email is required."}, status=status.HTTP_400_BAD_REQUEST)
    if role not in {OrganizationRole.ORG_ADMIN, OrganizationRole.OPERATOR, OrganizationRole.VIEWER}:
        return Response({"detail": "Invalid role."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            invitation = OrganizationInvitation.objects.create(
                tenant=organization.tenant,
                organization=organization,
                invited_by=request.user,
                email=email,
                role=role,
            )
            invite_link = _frontend_token_link("auth/accept-invitation", str(invitation.token))
            invitation_body = (
                f"Bonjour,\n\n"
                f"Vous avez ete invite a rejoindre l'organisation '{organization.name}' "
                f"(tenant '{organization.tenant.name}') avec le role '{invitation.role}'.\n"
                f"Token d'invitation: {invitation.token}\n"
                f"Lien d'acceptation: {invite_link or 'N/A'}\n\n"
                f"Invitation valide jusqu'au {invitation.expires_at}.\n"
            )
            _send_auth_email(
                to_email=invitation.email,
                subject="Invitation a rejoindre votre organisation Label CI",
                body=invitation_body,
            )
            email_sent = True
    except Exception as exc:
        logger.exception(
            "Failed to create invitation/send email organization=%s email=%s",
            organization.id,
            email,
        )
        return Response(
            {"detail": f"Unable to create invitation email delivery: {exc}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    payload = {
        "id": invitation.id,
        "status": invitation.status,
        "organization_id": organization.id,
        "email": invitation.email,
        "role": invitation.role,
        "expires_at": invitation.expires_at,
        "email_sent": email_sent,
    }
    if settings.DEBUG:
        payload["magic_link_token"] = str(invitation.token)

    return Response(
        payload,
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def accept_organization_invitation_api(request):
    token_text = str(request.data.get("token") or "").strip()
    if not token_text:
        return Response({"detail": "token is required."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        token_uuid = uuid.UUID(token_text)
    except ValueError:
        return Response({"detail": "Invalid token format."}, status=status.HTTP_400_BAD_REQUEST)

    invitation = (
        OrganizationInvitation.objects.select_related("tenant", "organization")
        .filter(token=token_uuid)
        .first()
    )
    if invitation is None:
        return Response({"detail": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)
    if invitation.status != OrganizationInvitation.STATUS_PENDING:
        return Response({"detail": f"Invitation is {invitation.status}."}, status=status.HTTP_409_CONFLICT)
    if invitation.is_expired:
        invitation.status = OrganizationInvitation.STATUS_EXPIRED
        invitation.save(update_fields=["status", "updated_at"])
        return Response({"detail": "Invitation expired."}, status=status.HTTP_410_GONE)

    user = request.user if request.user.is_authenticated else None
    if user is None:
        username = str(request.data.get("username") or invitation.email).strip()
        password = str(request.data.get("password") or "")
        if len(password) < 8:
            return Response({"detail": "password must be at least 8 characters for new users."}, status=status.HTTP_400_BAD_REQUEST)
        existing = User.objects.filter(username__iexact=username).first()
        if existing:
            return Response({"detail": "username already exists. Login first then accept invitation."}, status=status.HTTP_409_CONFLICT)
        user = User.objects.create_user(
            username=_unique_username(username),
            email=invitation.email,
            password=password,
            is_active=True,
        )
    else:
        if user.email and user.email.lower() != invitation.email.lower():
            return Response({"detail": "Invitation email does not match authenticated user email."}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        tenant_role = {
            OrganizationRole.ORG_ADMIN: TenantRole.ORG_ADMIN,
            OrganizationRole.OPERATOR: TenantRole.OPERATOR,
            OrganizationRole.VIEWER: TenantRole.VIEWER,
        }[invitation.role]
        membership, created = TenantMembership.objects.get_or_create(
            user=user,
            tenant=invitation.tenant,
            defaults={"role": tenant_role},
        )
        if not created:
            # Keep highest role only.
            ranking = {
                TenantRole.VIEWER: 10,
                TenantRole.OPERATOR: 20,
                TenantRole.ORG_ADMIN: 30,
                TenantRole.TENANT_ADMIN: 40,
            }
            if ranking.get(tenant_role, 0) > ranking.get(membership.role, 0):
                membership.role = tenant_role
                membership.save(update_fields=["role"])

        OrganizationMembership.objects.update_or_create(
            user=user,
            organization=invitation.organization,
            defaults={"role": invitation.role},
        )

        invitation.status = OrganizationInvitation.STATUS_ACCEPTED
        invitation.accepted_by = user
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["status", "accepted_by", "accepted_at", "updated_at"])

    return Response(
        {
            "status": "accepted",
            "tenant": invitation.tenant.code,
            "organization": invitation.organization.id,
            "user_id": user.id,
            "role": invitation.role,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_organizations_api(request):
    tenant_code = str(request.query_params.get("tenant_code") or "").strip()
    memberships = TenantMembership.objects.select_related("tenant").filter(user=request.user)
    if tenant_code:
        memberships = memberships.filter(tenant__code__iexact=tenant_code)

    tenant_ids = set()
    tenant_roles = {}
    for membership in memberships:
        tenant_ids.add(membership.tenant_id)
        tenant_roles[membership.tenant_id] = membership.role

    org_memberships = OrganizationMembership.objects.select_related("organization", "organization__tenant").filter(
        user=request.user
    )
    if tenant_ids:
        org_memberships = org_memberships.filter(organization__tenant_id__in=tenant_ids)

    organizations_by_tenant: dict[int, dict] = {}
    for membership in org_memberships:
        org = membership.organization
        entry = organizations_by_tenant.setdefault(
            org.tenant_id,
            {
                "tenant_id": org.tenant_id,
                "tenant_code": org.tenant.code,
                "tenant_name": org.tenant.name,
                "tenant_role": tenant_roles.get(org.tenant_id, TenantRole.VIEWER),
                "organizations": [],
            },
        )
        entry["organizations"].append(
            {
                "id": org.id,
                "name": org.name,
                "code": org.code,
                "role": membership.role,
            }
        )

    # Tenant admins can see all organizations of their tenant.
    for tenant_id, role in tenant_roles.items():
        if role == TenantRole.TENANT_ADMIN:
            tenant = Tenant.objects.filter(id=tenant_id).first()
            if tenant is None:
                continue
            entry = organizations_by_tenant.setdefault(
                tenant_id,
                {
                    "tenant_id": tenant.id,
                    "tenant_code": tenant.code,
                    "tenant_name": tenant.name,
                    "tenant_role": role,
                    "organizations": [],
                },
            )
            known = {org["id"] for org in entry["organizations"]}
            for org in Organization.objects.filter(tenant=tenant).order_by("id"):
                if org.id in known:
                    continue
                entry["organizations"].append(
                    {
                        "id": org.id,
                        "name": org.name,
                        "code": org.code,
                        "role": OrganizationRole.ORG_ADMIN,
                    }
                )

    results = sorted(organizations_by_tenant.values(), key=lambda item: item["tenant_code"])
    return Response({"count": len(results), "results": results}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
def login_api(request):
    identifier = str(
        request.data.get("identifier")
        or request.data.get("email")
        or request.data.get("username")
        or ""
    ).strip()
    password = str(request.data.get("password") or "")
    if not identifier or not password:
        return Response({"detail": "identifier/email/username and password are required."}, status=status.HTTP_400_BAD_REQUEST)

    username = identifier
    if "@" in identifier:
        user_by_email = User.objects.filter(email__iexact=identifier).first()
        if user_by_email is None:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
        username = user_by_email.get_username()

    user = authenticate(request=request, username=username, password=password)
    if user is None:
        return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
    if not user.is_active:
        return Response({"detail": "User account is inactive."}, status=status.HTTP_403_FORBIDDEN)

    refresh = RefreshToken.for_user(user)
    tenant_memberships = (
        TenantMembership.objects.select_related("tenant")
        .filter(user=user)
        .order_by("tenant_id")
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
                for membership in tenant_memberships
            ],
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_api(request):
    refresh_token = str(request.data.get("refresh") or "").strip()
    blacklisted = False
    if refresh_token:
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            blacklisted = True
        except Exception:
            # Blacklist app may be disabled. Logout remains client-side (drop JWT tokens).
            blacklisted = False
    django_logout(request)
    return Response({"status": "logged_out", "refresh_blacklisted": blacklisted}, status=status.HTTP_200_OK)


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def profile_api(request):
    user = request.user
    if request.method == "GET":
        return Response(AuthUserSerializer(user).data, status=status.HTTP_200_OK)

    allowed_fields = {"username", "email", "first_name", "last_name"}
    payload = {key: value for key, value in request.data.items() if key in allowed_fields}
    if "email" in payload:
        email = str(payload["email"] or "").strip().lower()
        if not email:
            return Response({"detail": "Email cannot be blank."}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(email__iexact=email).exclude(id=user.id).exists():
            return Response({"detail": "A user with this email already exists."}, status=status.HTTP_409_CONFLICT)
        payload["email"] = email
    if "username" in payload:
        username = str(payload["username"] or "").strip()
        if not username:
            return Response({"detail": "Username cannot be blank."}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(username__iexact=username).exclude(id=user.id).exists():
            return Response({"detail": "A user with this username already exists."}, status=status.HTTP_409_CONFLICT)
        payload["username"] = username
    if not payload:
        return Response({"detail": "No valid profile field provided."}, status=status.HTTP_400_BAD_REQUEST)

    serializer = AuthUserSerializer(user, data=payload, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password_api(request):
    serializer = ChangePasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user = request.user
    old_password = serializer.validated_data["old_password"]
    new_password = serializer.validated_data["new_password"]
    if not user.check_password(old_password):
        return Response({"detail": "Invalid old_password."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        validate_password(new_password, user=user)
    except DjangoValidationError as exc:
        return Response({"detail": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new_password)
    user.save(update_fields=["password"])
    return Response({"status": "password_changed"}, status=status.HTTP_200_OK)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def organization_users_api(request, organization_id: int):
    organization = Organization.objects.select_related("tenant").filter(id=organization_id).first()
    if organization is None:
        return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)
    if not _can_manage_org_members(request.user, organization):
        return Response({"detail": "Insufficient permissions for this organization."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        org_memberships = (
            OrganizationMembership.objects.select_related("user")
            .filter(organization=organization)
            .order_by("id")
        )
        user_ids = [membership.user_id for membership in org_memberships]
        tenant_roles = {
            row.user_id: row.role
            for row in TenantMembership.objects.filter(tenant=organization.tenant, user_id__in=user_ids)
        }
        role_assignments = (
            OrganizationCustomRoleAssignment.objects.select_related("role")
            .filter(organization=organization, user_id__in=user_ids)
            .order_by("id")
        )
        custom_roles_by_user = {}
        for assignment in role_assignments:
            custom_roles_by_user.setdefault(assignment.user_id, []).append(
                {
                    "id": assignment.role_id,
                    "name": assignment.role.name,
                }
            )

        results = []
        for membership in org_memberships:
            user = membership.user
            results.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "is_active": user.is_active,
                    "tenant_role": tenant_roles.get(user.id, TenantRole.VIEWER),
                    "organization_role": membership.role,
                    "custom_roles": custom_roles_by_user.get(user.id, []),
                }
            )
        return Response({"count": len(results), "results": results}, status=status.HTTP_200_OK)

    serializer = OrganizationUserCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    email = str(data["email"]).strip().lower()
    raw_username = str(data.get("username") or "").strip()
    first_name = str(data.get("first_name") or "").strip()
    last_name = str(data.get("last_name") or "").strip()
    password = data["password"]
    tenant_role = data.get("tenant_role", TenantRole.VIEWER)
    organization_role = data.get("organization_role", OrganizationRole.VIEWER)
    requested_custom_role_ids = list(dict.fromkeys(data.get("custom_role_ids") or []))

    minimum_tenant_role_from_org = {
        OrganizationRole.ORG_ADMIN: TenantRole.ORG_ADMIN,
        OrganizationRole.OPERATOR: TenantRole.OPERATOR,
        OrganizationRole.VIEWER: TenantRole.VIEWER,
    }[organization_role]
    if ROLE_RANK.get(tenant_role, 0) < ROLE_RANK.get(minimum_tenant_role_from_org, 0):
        tenant_role = minimum_tenant_role_from_org

    requester_tenant_membership = TenantMembership.objects.filter(
        user=request.user,
        tenant=organization.tenant,
    ).first()
    requester_tenant_role = requester_tenant_membership.role if requester_tenant_membership else TenantRole.VIEWER
    can_grant_tenant_admin = request.user.is_superuser or request.user.is_staff or requester_tenant_role == TenantRole.TENANT_ADMIN
    if tenant_role == TenantRole.TENANT_ADMIN and not can_grant_tenant_admin:
        return Response({"detail": "Only tenant admins can grant tenant_admin role."}, status=status.HTTP_403_FORBIDDEN)

    if raw_username and User.objects.filter(username__iexact=raw_username).exists():
        return Response({"detail": "A user with this username already exists."}, status=status.HTTP_409_CONFLICT)
    username = raw_username or _unique_username(email)

    try:
        validate_password(password)
    except DjangoValidationError as exc:
        return Response({"detail": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

    custom_roles = []
    if requested_custom_role_ids:
        custom_roles = list(
            OrganizationCustomRole.objects.filter(
                organization=organization,
                tenant=organization.tenant,
                is_active=True,
                id__in=requested_custom_role_ids,
            )
        )
        found_ids = {role.id for role in custom_roles}
        missing_ids = [role_id for role_id in requested_custom_role_ids if role_id not in found_ids]
        if missing_ids:
            return Response(
                {"detail": f"Invalid custom roles for this organization: {missing_ids}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_active=True,
            )
            TenantMembership.objects.update_or_create(
                user=user,
                tenant=organization.tenant,
                defaults={"role": tenant_role},
            )
            OrganizationMembership.objects.update_or_create(
                user=user,
                organization=organization,
                defaults={"role": organization_role},
            )
            for role in custom_roles:
                OrganizationCustomRoleAssignment.objects.get_or_create(
                    tenant=organization.tenant,
                    organization=organization,
                    role=role,
                    user=user,
                    defaults={"assigned_by": request.user},
                )
            role_names = ", ".join([organization_role, *[role.name for role in custom_roles]]) if custom_roles else organization_role
            account_body = (
                f"Bonjour,\n\n"
                f"Un compte a ete cree pour vous sur le tenant '{organization.tenant.name}' "
                f"dans l'organisation '{organization.name}'.\n"
                f"Identifiant: {user.username}\n"
                f"Email: {user.email}\n"
                f"Roles: {role_names}\n\n"
                f"Utilisez le mot de passe communique par votre administrateur pour vous connecter.\n"
            )
            _send_auth_email(
                to_email=user.email,
                subject="Votre compte Label CI a ete cree",
                body=account_body,
            )
            account_email_sent = True
    except Exception as exc:
        logger.exception(
            "Failed to create account/send email organization=%s email=%s",
            organization.id,
            email,
        )
        return Response(
            {"detail": f"Unable to complete account creation email delivery: {exc}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(
        {
            "status": "created",
            "user": AuthUserSerializer(user).data,
            "tenant_role": tenant_role,
            "organization_role": organization_role,
            "custom_roles": [{"id": role.id, "name": role.name} for role in custom_roles],
            "email_sent": account_email_sent,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def organization_custom_roles_api(request, organization_id: int):
    organization = Organization.objects.select_related("tenant").filter(id=organization_id).first()
    if organization is None:
        return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)
    if not _can_manage_org_members(request.user, organization):
        return Response({"detail": "Insufficient permissions for this organization."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        queryset = OrganizationCustomRole.objects.filter(
            tenant=organization.tenant,
            organization=organization,
        ).order_by("name", "id")
        return Response(
            {"count": queryset.count(), "results": OrganizationCustomRoleSerializer(queryset, many=True).data},
            status=status.HTTP_200_OK,
        )

    name = str(request.data.get("name") or "").strip()
    description = str(request.data.get("description") or "").strip()
    raw_is_active = request.data.get("is_active", True)
    if isinstance(raw_is_active, bool):
        is_active = raw_is_active
    else:
        is_active = str(raw_is_active).strip().lower() in {"1", "true", "yes", "on"}
    if not name:
        return Response({"detail": "name is required."}, status=status.HTTP_400_BAD_REQUEST)
    if OrganizationCustomRole.objects.filter(organization=organization, name__iexact=name).exists():
        return Response({"detail": "A role with this name already exists in this organization."}, status=status.HTTP_409_CONFLICT)

    role = OrganizationCustomRole.objects.create(
        tenant=organization.tenant,
        organization=organization,
        name=name,
        description=description,
        is_active=is_active,
        created_by=request.user,
    )
    return Response(OrganizationCustomRoleSerializer(role).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def assign_custom_role_api(request, organization_id: int, role_id: int):
    organization = Organization.objects.select_related("tenant").filter(id=organization_id).first()
    if organization is None:
        return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)
    if not _can_manage_org_members(request.user, organization):
        return Response({"detail": "Insufficient permissions for this organization."}, status=status.HTTP_403_FORBIDDEN)

    role = (
        OrganizationCustomRole.objects.filter(
            id=role_id,
            tenant=organization.tenant,
            organization=organization,
        )
        .first()
    )
    if role is None:
        return Response({"detail": "Role not found for this organization."}, status=status.HTTP_404_NOT_FOUND)

    try:
        user_id = int(request.data.get("user_id"))
    except (TypeError, ValueError):
        return Response({"detail": "user_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    is_assigned = str(request.data.get("assigned", "true")).strip().lower() in {"1", "true", "yes", "on"}
    membership = OrganizationMembership.objects.select_related("user").filter(
        organization=organization,
        user_id=user_id,
    ).first()
    if membership is None:
        return Response({"detail": "User is not a member of this organization."}, status=status.HTTP_400_BAD_REQUEST)

    if is_assigned:
        assignment, created = OrganizationCustomRoleAssignment.objects.get_or_create(
            tenant=organization.tenant,
            organization=organization,
            role=role,
            user=membership.user,
            defaults={"assigned_by": request.user},
        )
        if not created and assignment.assigned_by_id != request.user.id:
            assignment.assigned_by = request.user
            assignment.save(update_fields=["assigned_by"])
    else:
        OrganizationCustomRoleAssignment.objects.filter(
            tenant=organization.tenant,
            organization=organization,
            role=role,
            user=membership.user,
        ).delete()

    assigned_roles = OrganizationCustomRoleAssignment.objects.select_related("role").filter(
        organization=organization,
        user=membership.user,
    )
    return Response(
        {
            "status": "assigned" if is_assigned else "removed",
            "user_id": membership.user_id,
            "organization_id": organization.id,
            "roles": [{"id": row.role_id, "name": row.role.name} for row in assigned_roles],
        },
        status=status.HTTP_200_OK,
    )
