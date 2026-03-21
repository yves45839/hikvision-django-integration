from __future__ import annotations

from employees.models import Organization, OrganizationMembership, OrganizationRole
from tenants.models import Tenant, TenantMembership, TenantRole


ROLE_RANK = {
    TenantRole.VIEWER: 10,
    TenantRole.OPERATOR: 20,
    TenantRole.ORG_ADMIN: 30,
    TenantRole.TENANT_ADMIN: 40,
}


def resolve_tenant(tenant_code: str) -> Tenant | None:
    return Tenant.objects.filter(code__iexact=str(tenant_code or "").strip()).first()


def has_tenant_role(user, tenant: Tenant, minimum_role: str = TenantRole.VIEWER) -> bool:
    if user and user.is_authenticated and (user.is_superuser or user.is_staff):
        return True
    if not user or not user.is_authenticated or tenant is None:
        return False
    membership = TenantMembership.objects.filter(user=user, tenant=tenant).first()
    if membership is None:
        return False
    current_rank = ROLE_RANK.get(membership.role, 0)
    required_rank = ROLE_RANK.get(minimum_role, 0)
    return current_rank >= required_rank


def has_organization_role(
    user,
    organization: Organization,
    allowed_org_roles: tuple[str, ...] = (OrganizationRole.ORG_ADMIN, OrganizationRole.OPERATOR),
) -> bool:
    if user and user.is_authenticated and (user.is_superuser or user.is_staff):
        return True
    if not user or not user.is_authenticated or organization is None:
        return False
    if has_tenant_role(user, organization.tenant, TenantRole.TENANT_ADMIN):
        return True
    return OrganizationMembership.objects.filter(
        user=user,
        organization=organization,
        role__in=allowed_org_roles,
    ).exists()
