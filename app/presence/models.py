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


class EmployeePushToken(models.Model):
    """Jeton push Expo d'une installation de l'app (un employé peut avoir
    plusieurs téléphones ; un téléphone réinstallé change de token)."""

    PLATFORM_CHOICES = (("ios", "iOS"), ("android", "Android"), ("unknown", "Unknown"))

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="push_tokens")
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=16, choices=PLATFORM_CHOICES, default="unknown")
    installation_id = models.CharField(max_length=64, blank=True, default="")
    app_version = models.CharField(max_length=64, blank=True, default="")
    locale = models.CharField(max_length=8, blank=True, default="")
    timezone = models.CharField(max_length=64, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["employee", "is_active"]),
            models.Index(fields=["installation_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id}:{self.platform}:{self.token[:16]}"


class PunchReminderLog(models.Model):
    """Journal d'idempotence des rappels de pointage — au plus un envoi par
    (employé, date locale, type), avec statut par canal pour le diagnostic."""

    KIND_PRE_START_WARNING = "pre_start_warning"
    KIND_LATE_REMINDER = "late_reminder"
    KIND_CHOICES = (
        (KIND_PRE_START_WARNING, "Pre-start warning"),
        (KIND_LATE_REMINDER, "Late reminder"),
    )

    CHANNEL_SENT = "sent"
    CHANNEL_FAILED = "failed"
    CHANNEL_SKIPPED = "skipped"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="punch_reminders")
    date = models.DateField()
    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    expected_start_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    push_status = models.CharField(max_length=16, default=CHANNEL_SKIPPED)
    email_status = models.CharField(max_length=16, default=CHANNEL_SKIPPED)
    sms_status = models.CharField(max_length=16, default=CHANNEL_SKIPPED)
    errors = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "date", "kind"], name="uq_punch_reminder_once"
            ),
        ]
        indexes = [models.Index(fields=["date", "kind"])]

    def __str__(self) -> str:
        return f"{self.employee_id}:{self.date}:{self.kind}"


class TenantNotificationSettings(models.Model):
    """Canaux de rappel de pointage activés pour le tenant."""

    tenant = models.OneToOneField(
        Tenant, on_delete=models.CASCADE, related_name="punch_notification_settings"
    )
    reminders_enabled = models.BooleanField(default=True)
    warning_enabled = models.BooleanField(default=True)
    late_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"NotifSettings<{self.tenant_id}>"
