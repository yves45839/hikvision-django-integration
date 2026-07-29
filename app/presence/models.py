"""Modèles du pointage mobile (sites, invitations employé)."""
import hashlib
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from employees.models import Employee
from tenants.models import Tenant


def default_mobile_invitation_expiry():
    return timezone.now() + timezone.timedelta(days=7)


def hash_invitation_secret(secret: str) -> str:
    """Empreinte SHA-256 du secret d'invitation — seul l'empreinte est stockée."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class EmployeeInvitation(models.Model):
    """Invitation d'un employé à créer son compte app mobile.

    Le secret circule uniquement dans l'email (deep link) ; la base ne
    conserve que son empreinte : une fuite de base n'expose pas les
    invitations non utilisées.
    """

    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_EXPIRED = "expired"
    STATUS_REVOKED = "revoked"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_REVOKED, "Revoked"),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="mobile_invitations")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="mobile_invitations")
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_mobile_invitations",
    )
    expires_at = models.DateTimeField(default=default_mobile_invitation_expiry)
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["employee", "status"]),
        ]

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def __str__(self) -> str:
        return f"{self.employee_id}:{self.email}:{self.status}"


class Site(models.Model):
    """Site de pointage : zone géographique où le pointage mobile est valide.

    V1 : tout site actif du tenant vaut pour tous ses employés.
    # future: M2M site↔department pour restreindre par équipe.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="punch_sites")
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True, default="")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    radius_m = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uq_punch_site_tenant_name"),
        ]
        indexes = [
            models.Index(fields=["tenant", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.name}"
