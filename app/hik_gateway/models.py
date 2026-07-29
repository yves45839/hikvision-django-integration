from django.conf import settings
from django.db import models

from tenants.models import Tenant


class Gateway(models.Model):
    KIND_HIKVISION = "hikvision"
    KIND_MOBILE_VIRTUAL = "mobile_virtual"
    KIND_CHOICES = (
        (KIND_HIKVISION, "Hikvision"),
        (KIND_MOBILE_VIRTUAL, "Mobile virtual"),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="hik_gateways")
    kind = models.CharField(max_length=32, choices=KIND_CHOICES, default=KIND_HIKVISION)
    base_url = models.URLField()
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["tenant"]) ]

    # Capacités dérivées du kind : les services sélectionnent par capacité,
    # jamais par exclusion d'URL — un appareil virtuel (pointage mobile) n'est
    # ni synchronisable ni joignable en HTTP.
    @property
    def supports_sync(self) -> bool:
        return self.kind == self.KIND_HIKVISION

    @property
    def supports_health_check(self) -> bool:
        return self.kind == self.KIND_HIKVISION

    @property
    def supports_remote_commands(self) -> bool:
        return self.kind == self.KIND_HIKVISION

    def __str__(self):
        return f"Gateway<{self.tenant_id}:{self.base_url}>"


class Device(models.Model):
    KIND_HIKVISION = "hikvision"
    KIND_MOBILE_VIRTUAL = "mobile_virtual"
    KIND_CHOICES = (
        (KIND_HIKVISION, "Hikvision"),
        (KIND_MOBILE_VIRTUAL, "Mobile virtual"),
    )

    gateway = models.ForeignKey(Gateway, on_delete=models.CASCADE, related_name="devices")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="hik_devices")
    kind = models.CharField(max_length=32, choices=KIND_CHOICES, default=KIND_HIKVISION)
    serial_number = models.CharField(max_length=128)
    dev_index = models.CharField(max_length=64)
    device_id = models.CharField(max_length=128, blank=True, default="")
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
            models.UniqueConstraint(fields=["tenant", "dev_index"], name="uq_hik_device_tenant_dev_index"),
        ]
        indexes = [
            models.Index(fields=["tenant", "serial_number"]),
            models.Index(fields=["dev_index"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.serial_number} ({self.dev_index})"


class RawEvent(models.Model):
    """
    PHASE 11.3 — Déduplication robuste
    Utilise dedupe_key unique pour éviter les doublons d'événements.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="hik_raw_events")
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="raw_events", null=True, blank=True)
    dev_index = models.CharField(max_length=64)
    received_at = models.DateTimeField(auto_now_add=True)
    event_type = models.CharField(max_length=64)
    event_datetime = models.DateTimeField()
    major_event_type = models.IntegerField(null=True, blank=True)
    sub_event_type = models.IntegerField(null=True, blank=True)
    serial_no = models.IntegerField(null=True, blank=True)
    front_serial_no = models.IntegerField(null=True, blank=True)
    employee_no = models.CharField(max_length=128, blank=True, default="")
    employee_no_string = models.CharField(max_length=128, blank=True, default="")
    card_no = models.CharField(max_length=128, blank=True, default="")
    card_reader_no = models.IntegerField(null=True, blank=True)
    door_no = models.IntegerField(null=True, blank=True)
    attendance_status = models.CharField(max_length=64, blank=True, default="")
    dedupe_key = models.CharField(max_length=255, unique=True)
    payload = models.JSONField()

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "dev_index", "event_datetime"]),
            models.Index(fields=["event_type"]),
            models.Index(fields=["dedupe_key"]),  # Index pour accès rapide à dedupe_key
        ]

    def __str__(self):
        return f"{self.event_type}@{self.dev_index}:{self.event_datetime}"


class AttendanceLog(models.Model):
    SOURCE_REALTIME = "realtime"
    SOURCE_CATCHUP = "catchup"
    SOURCE_MOBILE = "mobile"
    SOURCE_CHOICES = [
        (SOURCE_REALTIME, "Realtime"),
        (SOURCE_CATCHUP, "Catchup"),
        (SOURCE_MOBILE, "Mobile"),
    ]
    ACTION_CHECK_IN = "CHECK_IN"
    ACTION_CHECK_OUT = "CHECK_OUT"
    ACTION_BREAK_IN = "BREAK_IN"
    ACTION_BREAK_OUT = "BREAK_OUT"
    ACTION_OVERTIME_IN = "OVERTIME_IN"
    ACTION_OVERTIME_OUT = "OVERTIME_OUT"
    ACTION_ACCESS_DENIED = "ACCESS_DENIED"
    ACTION_UNKNOWN = "UNKNOWN"
    ACTION_CHOICES = [
        (ACTION_CHECK_IN, "Check-in"),
        (ACTION_CHECK_OUT, "Check-out"),
        (ACTION_BREAK_IN, "Break-in"),
        (ACTION_BREAK_OUT, "Break-out"),
        (ACTION_OVERTIME_IN, "Overtime-in"),
        (ACTION_OVERTIME_OUT, "Overtime-out"),
        (ACTION_ACCESS_DENIED, "Access denied"),
        (ACTION_UNKNOWN, "Unknown"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="hik_attendance_logs")
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.SET_NULL,
        related_name="hik_attendance_logs",
        null=True,
        blank=True,
    )
    person_id = models.CharField(max_length=128, blank=True, default="")
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="attendance_logs")
    timestamp = models.DateTimeField()
    attendance_type = models.CharField(max_length=64)
    attendance_status = models.CharField(max_length=64, blank=True, default="")
    normalized_action = models.CharField(max_length=32, choices=ACTION_CHOICES, default=ACTION_UNKNOWN)
    direction = models.CharField(max_length=16, default="UNKNOWN")
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES)
    raw_event = models.OneToOneField(RawEvent, on_delete=models.CASCADE, related_name="attendance_log")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "timestamp"]),
            models.Index(fields=["person_id"]),
            models.Index(fields=["attendance_type"]),
            models.Index(fields=["normalized_action"]),
        ]


class AttendanceCorrection(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="attendance_corrections")
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="attendance_corrections",
    )
    work_date = models.DateField()
    arrival_time = models.TimeField(null=True, blank=True)
    departure_time = models.TimeField(null=True, blank=True)
    break_start_time = models.TimeField(null=True, blank=True)
    break_end_time = models.TimeField(null=True, blank=True)
    overtime_hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_attendance_corrections",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_attendance_corrections",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "employee", "work_date"],
                name="uq_hik_attendance_correction_employee_day",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "work_date"]),
            models.Index(fields=["tenant", "employee", "work_date"]),
        ]


class AttendanceCorrectionLog(models.Model):
    ACTION_CREATE = "CREATE"
    ACTION_UPDATE = "UPDATE"
    ACTION_CHOICES = [
        (ACTION_CREATE, "Create"),
        (ACTION_UPDATE, "Update"),
    ]

    correction = models.ForeignKey(
        AttendanceCorrection,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="attendance_correction_logs")
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="attendance_correction_logs",
    )
    work_date = models.DateField()
    action = models.CharField(max_length=16, choices=ACTION_CHOICES)
    payload = models.JSONField(default=dict, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendance_correction_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "employee", "work_date"]),
            models.Index(fields=["tenant", "created_at"]),
        ]


class DeviceCursor(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="hik_device_cursors")
    device = models.OneToOneField(Device, on_delete=models.CASCADE, related_name="cursor")
    last_event_time = models.DateTimeField(null=True, blank=True)
    last_serial_no = models.IntegerField(null=True, blank=True)
    last_search_id = models.CharField(max_length=128, blank=True, default="")
    last_search_result_position = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["last_event_time"])]


class DeviceReaderConfig(models.Model):
    DIRECTION_IN = "IN"
    DIRECTION_OUT = "OUT"
    DIRECTION_CHOICES = [
        (DIRECTION_IN, "In"),
        (DIRECTION_OUT, "Out"),
    ]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="reader_configs")
    door_no = models.IntegerField()
    card_reader_no = models.IntegerField()
    direction_default = models.CharField(max_length=8, choices=DIRECTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["device", "door_no", "card_reader_no"],
                name="uq_hik_reader_direction",
            )
        ]
        indexes = [models.Index(fields=["device", "door_no", "card_reader_no"], name="idx_hik_access_dev_door_reader")]

