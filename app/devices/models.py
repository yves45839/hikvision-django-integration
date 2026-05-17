from django.db import models
from devices.encryption import encrypt_value, decrypt_value
from django.contrib.auth import get_user_model
from tenants.models import Tenant


User = get_user_model()


ISUP_PORT_CHOICES = (
    (7660, '7660'),
    (7661, '7661'),
)

class Device(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='devices', null=True, blank=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)

    ip_address = models.GenericIPAddressField(default='213.156.133.202', editable=False)
    port = models.PositiveIntegerField(choices=ISUP_PORT_CHOICES, default=7661)
    serial_number = models.CharField(max_length=31, unique=True)

    dev_index = models.CharField(max_length=64, unique=True)

    device_id = models.CharField(max_length=100, blank=True, default='')
    name = models.CharField(max_length=255, blank=True, default='')
    model = models.CharField(max_length=100, blank=True, default='')
    protocol = models.CharField(max_length=50, blank=True, default='')
    status = models.CharField(max_length=30, blank=True, default='')
    device_username = models.CharField(max_length=150, blank=True, default='')
    device_password_encrypted = models.CharField(max_length=500, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)


    @property
    def device_password(self):
        """0.6: Decrypt device password on access."""
        return decrypt_value(self.device_password_encrypted)
    
    @device_password.setter
    def device_password(self, value):
        """0.6: Encrypt device password on assignment."""
        self.device_password_encrypted = encrypt_value(value)
    
    def __str__(self):
        return self.name or self.device_id or self.dev_index


class DeviceOrganizationBinding(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="organization_bindings")
    organization = models.ForeignKey("employees.Organization", on_delete=models.CASCADE, related_name="device_bindings")
    is_primary = models.BooleanField(default=False)
    assigned_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_device_bindings",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["device", "organization"], name="uq_device_org_binding"),
        ]
        indexes = [
            models.Index(fields=["organization", "is_primary"]),
            models.Index(fields=["device", "is_primary"]),
        ]

    def clean(self):
        if self.device.tenant_id != self.organization.tenant_id:
            from django.core.exceptions import ValidationError

            raise ValidationError("Le device et l'organisation doivent appartenir au meme tenant.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.device_id}:{self.organization_id}"


class DeviceOnboardingJob(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_MANUAL_REVIEW = "manual_review"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_MANUAL_REVIEW, "Manual review"),
    )

    REVIEW_NONE = ""
    REVIEW_TENANT_INACTIVE = "tenant_inactive"
    REVIEW_DOMAIN_NOT_VERIFIED = "domain_not_verified"
    REVIEW_QUOTA_EXCEEDED = "quota_exceeded"
    REVIEW_PERMISSION_DENIED = "permission_denied"
    REVIEW_CHOICES = (
        (REVIEW_NONE, "None"),
        (REVIEW_TENANT_INACTIVE, "Tenant inactive"),
        (REVIEW_DOMAIN_NOT_VERIFIED, "Domain not verified"),
        (REVIEW_QUOTA_EXCEEDED, "Quota exceeded"),
        (REVIEW_PERMISSION_DENIED, "Permission denied"),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="device_onboarding_jobs")
    organization = models.ForeignKey("employees.Organization", on_delete=models.CASCADE, related_name="device_onboarding_jobs")
    requested_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_device_onboarding_jobs",
    )
    device = models.ForeignKey(Device, null=True, blank=True, on_delete=models.SET_NULL, related_name="onboarding_jobs")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    review_reason = models.CharField(max_length=64, choices=REVIEW_CHOICES, default=REVIEW_NONE, blank=True)
    error_message = models.TextField(blank=True, default="")
    gateway_status = models.JSONField(default=dict, blank=True)
    request_payload = models.JSONField(default=dict, blank=True)

    sn = models.CharField(max_length=31)
    dev_name = models.CharField(max_length=255)
    dev_type = models.CharField(max_length=64, default="AccessControl")
    device_username = models.CharField(max_length=150, blank=True, default="")
    device_password_encrypted = models.CharField(max_length=500, blank=True, default="")

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["created_at"]),
        ]


    @property
    def device_password(self):
        """0.6: Decrypt device password on access."""
        return decrypt_value(self.device_password_encrypted)
    
    @device_password.setter
    def device_password(self, value):
        """0.6: Encrypt device password on assignment."""
        self.device_password_encrypted = encrypt_value(value)
    
    def __str__(self):
        return f"{self.id}:{self.tenant.code}:{self.sn}:{self.status}"
