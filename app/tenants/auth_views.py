from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from employees.models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    OrganizationRole,
)
from tenants.models import (
    EmailVerificationToken,
    PaymentStatus,
    Tenant,
    TenantMembership,
    TenantRole,
)
from tenants.services import has_organization_role, resolve_tenant


User = get_user_model()


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

        verification = EmailVerificationToken.objects.create(user=user, tenant=tenant)

    return Response(
        {
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
            # In production this token should be emailed, not returned.
            "email_verification_token": str(verification.token),
            "email_verification_expires_at": verification.expires_at,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def verify_email_api(request):
    token_text = str(request.data.get("token") or "").strip()
    if not token_text:
        return Response({"detail": "token is required."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        token_uuid = uuid.UUID(token_text)
    except ValueError:
        return Response({"detail": "Invalid token format."}, status=status.HTTP_400_BAD_REQUEST)

    verification = EmailVerificationToken.objects.select_related("user", "tenant").filter(token=token_uuid).first()
    if verification is None:
        return Response({"detail": "Token not found."}, status=status.HTTP_404_NOT_FOUND)
    if verification.is_used:
        return Response({"detail": "Token already used."}, status=status.HTTP_409_CONFLICT)
    if verification.is_expired:
        verification.is_used = True
        verification.used_at = verification.expires_at
        verification.save(update_fields=["is_used", "used_at"])
        return Response({"detail": "Token expired."}, status=status.HTTP_410_GONE)

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

    invitation = OrganizationInvitation.objects.create(
        tenant=organization.tenant,
        organization=organization,
        invited_by=request.user,
        email=email,
        role=role,
    )
    return Response(
        {
            "id": invitation.id,
            "status": invitation.status,
            "organization_id": organization.id,
            "email": invitation.email,
            "role": invitation.role,
            "expires_at": invitation.expires_at,
            # In production this is sent by email.
            "magic_link_token": str(invitation.token),
        },
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
