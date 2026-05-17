import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone


User = get_user_model()


class TenantRole(models.TextChoices):
    TENANT_ADMIN = "tenant_admin", "Tenant admin"
    ORG_ADMIN = "org_admin", "Organization admin"
    OPERATOR = "operator", "Operator"
    VIEWER = "viewer", "Viewer"


class PaymentStatus(models.TextChoices):
    NOT_REQUIRED = "not_required", "Not required"
    PENDING = "pending", "Pending"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"


def default_email_verification_expiry():
    return timezone.now() + timezone.timedelta(hours=24)


class Tenant(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    domain = models.CharField(max_length=255, blank=True, default="")
    is_domain_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    device_quota = models.PositiveIntegerField(default=50)
    payment_status = models.CharField(
        max_length=16,
        choices=PaymentStatus.choices,
        default=PaymentStatus.NOT_REQUIRED,
    )
    requires_manual_review = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class TenantMembership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tenant_memberships")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=32, choices=TenantRole.choices, default=TenantRole.VIEWER)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "tenant"], name="uq_tenant_membership_user_tenant"),
        ]
        indexes = [
            models.Index(fields=["tenant", "role"]),
            models.Index(fields=["user", "role"]),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.tenant.code}:{self.role}"


class EmailVerificationToken(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_verification_tokens",
    )
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="email_verification_tokens")
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    otp_code = models.CharField(max_length=6, blank=True, default="", db_index=True)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField(default=default_email_verification_expiry)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "is_used"]),
            models.Index(fields=["expires_at"]),
        ]

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def __str__(self):
        return f"{self.tenant.code}:{self.user_id}:{self.token}"


def default_password_reset_expiry():
    return timezone.now() + timezone.timedelta(minutes=30)


class PasswordResetToken(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="password_reset_tokens",
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    otp_code = models.CharField(max_length=6, db_index=True)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField(default=default_password_reset_expiry)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "is_used"]),
            models.Index(fields=["expires_at"]),
        ]

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def __str__(self):
        return f"{self.user_id}:{self.token}"


class OrganizationCustomRole(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="organization_custom_roles")
    organization = models.ForeignKey(
        "employees.Organization",
        on_delete=models.CASCADE,
        related_name="custom_roles",
    )
    name = models.CharField(max_length=64)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_custom_roles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="uq_org_custom_role_name",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "organization", "is_active"]),
            models.Index(fields=["organization", "name"]),
        ]

    def __str__(self):
        return f"{self.organization_id}:{self.name}"


class OrganizationCustomRoleAssignment(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="organization_custom_role_assignments")
    organization = models.ForeignKey(
        "employees.Organization",
        on_delete=models.CASCADE,
        related_name="custom_role_assignments",
    )
    role = models.ForeignKey(
        OrganizationCustomRole,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization_custom_role_assignments",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_organization_custom_roles",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["role", "user"], name="uq_org_custom_role_assignment_role_user"),
        ]
        indexes = [
            models.Index(fields=["tenant", "organization"]),
            models.Index(fields=["organization", "user"]),
        ]

    def __str__(self):
        return f"{self.organization_id}:{self.user_id}:{self.role_id}"


class ConsentLog(models.Model):
    """RGPD art. 6 — Journal des consentements recueillis au signup."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="consent_logs",
    )
    email = models.EmailField()
    consent_tos = models.BooleanField(default=False)
    consent_privacy = models.BooleanField(default=False)
    consent_marketing = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["email", "created_at"])]

    def __str__(self):
        return f"ConsentLog({self.email}, {self.created_at})"


class ConsentLog(models.Model):
    """
    PHASE 6.4 — Consent Log (RGPD)
    Enregistre les consentements explicites de l'utilisateur pour TOS, Privacy Policy, Marketing.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consent_logs",
    )
    email = models.EmailField()  # Garder l'email même si user supprimé
    consent_tos = models.BooleanField(default=False)
    consent_privacy = models.BooleanField(default=False)
    consent_marketing = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["email", "created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"{self.email}:{self.created_at}"


class ConsentLog(models.Model):
    """RGPD art. 6 — Journal des consentements recueillis au signup."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="consent_logs",
    )
    email = models.EmailField()
    consent_tos = models.BooleanField(default=False)
    consent_privacy = models.BooleanField(default=False)
    consent_marketing = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["email", "created_at"])]

    def __str__(self):
        return f"ConsentLog({self.email}, {self.created_at})"
