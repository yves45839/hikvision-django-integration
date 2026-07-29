"""Helpers to scope billing requests to the user's active tenant."""
from __future__ import annotations

from typing import Optional

from rest_framework.exceptions import PermissionDenied

from tenants.models import Tenant, TenantMembership, TenantRole


_BILLING_ALLOWED_ROLES = {TenantRole.TENANT_ADMIN}


def get_request_tenant(request) -> Tenant:
    """Resolve the tenant the user is acting on for this request.

    Strategy:
    1. ?tenant_code=XXX  query param (when explicit)
    2. X-Tenant-Code     header
    3. The user's primary membership.

    Raises 403 if the user has no membership for the chosen tenant.
    """
    user = request.user
    if not (user and user.is_authenticated):
        raise PermissionDenied("Authentication required.")

    code = (
        request.query_params.get("tenant_code")
        or request.headers.get("X-Tenant-Code")
        or ""
    ).strip()

    # Le rôle "employee" (app mobile) n'a aucun accès à la facturation.
    memberships = (
        TenantMembership.objects
        .select_related("tenant")
        .filter(user=user)
        .exclude(role=TenantRole.EMPLOYEE)
    )
    if code:
        membership = memberships.filter(tenant__code=code).first()
    else:
        membership = memberships.order_by("-is_primary", "id").first()

    if not membership:
        raise PermissionDenied("You have no tenant membership.")
    return membership.tenant


def assert_can_manage_billing(request, tenant: Optional[Tenant] = None) -> Tenant:
    """Only tenant admins can create/cancel subscriptions or one-time payments."""
    target = tenant or get_request_tenant(request)
    membership = TenantMembership.objects.filter(
        user=request.user, tenant=target,
    ).first()
    if not membership or membership.role not in _BILLING_ALLOWED_ROLES:
        raise PermissionDenied("Only tenant admins can manage billing.")
    return target
