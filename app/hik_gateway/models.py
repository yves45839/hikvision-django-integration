from django.db import models

from tenants.models import Tenant


class Gateway(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="hik_gateways")
    base_url = models.URLField()
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["tenant"]) ]

    def __str__(self):
        return f"Gateway<{self.tenant_id}:{self.base_url}>"


class Device(models.Model):
    gateway = models.ForeignKey(Gateway, on_delete=models.CASCADE, related_name="devices")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="hik_devices")
    serial_number = models.CharField(max_length=128)
    dev_index = models.CharField(max_length=64, unique=True)
    device_name = models.CharField(max_length=255, blank=True, default="")
    protocol_type = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=32, blank=True, default="")
    offline_hint = models.CharField(max_length=255, blank=True, default="")
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "serial_number"], name="uq_hik_device_tenant_sn"),
        ]
        indexes = [
            models.Index(fields=["tenant", "serial_number"]),
            models.Index(fields=["dev_index"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.serial_number} ({self.dev_index})"


class RawEvent(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="hik_raw_events")
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="raw_events", null=True, blank=True)
    dev_index = models.CharField(max_length=64)
    received_at = models.DateTimeField(auto_now_add=True)
    event_type = models.CharField(max_length=64)
    event_datetime = models.DateTimeField()
    dedupe_key = models.CharField(max_length=255, unique=True)
    payload = models.JSONField()

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "dev_index", "event_datetime"]),
            models.Index(fields=["event_type"]),
        ]


class AttendanceLog(models.Model):
    SOURCE_REALTIME = "realtime"
    SOURCE_CATCHUP = "catchup"
    SOURCE_CHOICES = [
        (SOURCE_REALTIME, "Realtime"),
        (SOURCE_CATCHUP, "Catchup"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="hik_attendance_logs")
    person_id = models.CharField(max_length=128, blank=True, default="")
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="attendance_logs")
    timestamp = models.DateTimeField()
    attendance_type = models.CharField(max_length=64)
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES)
    raw_event = models.OneToOneField(RawEvent, on_delete=models.CASCADE, related_name="attendance_log")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "timestamp"]),
            models.Index(fields=["person_id"]),
            models.Index(fields=["attendance_type"]),
        ]


class DeviceCursor(models.Model):
    device = models.OneToOneField(Device, on_delete=models.CASCADE, related_name="cursor")
    last_event_time = models.DateTimeField(null=True, blank=True)
    last_search_id = models.CharField(max_length=128, blank=True, default="")
    last_result_position = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["last_event_time"])]
