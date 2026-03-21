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
