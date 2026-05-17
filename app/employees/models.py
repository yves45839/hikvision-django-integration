import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from devices.models import Device
from tenants.models import Tenant


class Organization(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="organizations")
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uq_organization_tenant_code"),
        ]
        indexes = [
            models.Index(fields=["tenant", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.tenant.code}:{self.name}"


class OrganizationRole(models.TextChoices):
    ORG_ADMIN = "org_admin", "Org Admin"
    OPERATOR = "operator", "Operator"
    VIEWER = "viewer", "Viewer"


def default_invitation_expiry():
    return timezone.now() + timezone.timedelta(days=7)


class OrganizationMembership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="organization_memberships")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=32, choices=OrganizationRole.choices, default=OrganizationRole.VIEWER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "organization"], name="uq_org_membership_user_org"),
        ]
        indexes = [
            models.Index(fields=["organization", "role"]),
            models.Index(fields=["user", "role"]),
        ]

    @property
    def tenant_id(self):
        return self.organization.tenant_id

    def __str__(self) -> str:
        return f"{self.user_id}:{self.organization_id}:{self.role}"


class OrganizationInvitation(models.Model):
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

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="organization_invitations")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invitations")
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_organization_invitations",
    )
    email = models.EmailField()
    role = models.CharField(max_length=32, choices=OrganizationRole.choices, default=OrganizationRole.VIEWER)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    expires_at = models.DateTimeField(default=default_invitation_expiry)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="accepted_organization_invitations",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["email"]),
        ]

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def __str__(self) -> str:
        return f"{self.organization_id}:{self.email}:{self.role}"


class Planning(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="plannings")
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=64)
    description = models.TextField(blank=True, default="")
    timezone = models.CharField(max_length=64, blank=True, default="UTC")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uq_planning_tenant_code"),
        ]
        indexes = [
            models.Index(fields=["tenant", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.tenant.code}:{self.name}"


class PlanningDailySlot(models.Model):
    SLOT_TYPE_WORK = "work"
    SLOT_TYPE_SHIFT = "shift"
    SLOT_TYPE_REST = "rest"
    SLOT_TYPE_CHOICES = (
        (SLOT_TYPE_WORK, "Work"),
        (SLOT_TYPE_SHIFT, "Shift"),
        (SLOT_TYPE_REST, "Rest"),
    )
    DAY_CHOICES = (
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    )

    planning = models.ForeignKey(Planning, on_delete=models.CASCADE, related_name="daily_slots")
    day_of_week = models.PositiveSmallIntegerField(choices=DAY_CHOICES)
    slot_type = models.CharField(max_length=16, choices=SLOT_TYPE_CHOICES, default=SLOT_TYPE_WORK)
    start_time = models.TimeField()
    end_time = models.TimeField()
    label = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["planning", "day_of_week", "slot_type", "start_time", "end_time"],
                name="uq_planning_daily_slot",
            ),
        ]
        indexes = [
            models.Index(fields=["planning", "day_of_week"]),
        ]

    def clean(self):
        if self.day_of_week < 0 or self.day_of_week > 6:
            raise ValidationError({"day_of_week": "Le jour doit etre compris entre 0 (lundi) et 6 (dimanche)."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.planning.code}:{self.day_of_week}:{self.start_time}-{self.end_time}"


class WorkShift(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="work_shifts")
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=64, blank=True, default="")
    description = models.TextField(blank=True, default="")
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    break_start_time = models.TimeField(null=True, blank=True)
    break_end_time = models.TimeField(null=True, blank=True)
    overtime_minutes = models.PositiveIntegerField(default=0)
    late_allowable_minutes = models.PositiveIntegerField(default=0)
    early_leave_allowable_minutes = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uq_work_shift_tenant_code"),
            models.UniqueConstraint(fields=["tenant", "name"], name="uq_work_shift_tenant_name"),
        ]
        indexes = [
            models.Index(fields=["tenant", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.tenant.code}:{self.name}"

    def clean(self):
        if bool(self.start_time) != bool(self.end_time):
            raise ValidationError({"start_time": "start_time et end_time doivent etre renseignes ensemble."})
        if bool(self.break_start_time) != bool(self.break_end_time):
            raise ValidationError(
                {"break_start_time": "break_start_time et break_end_time doivent etre renseignes ensemble."}
            )

        if self.start_time and self.end_time and self.start_time == self.end_time:
            raise ValidationError({"end_time": "L'heure de fin doit etre differente de l'heure de debut."})

        if self.break_start_time and self.break_end_time and self.break_start_time == self.break_end_time:
            raise ValidationError({"break_end_time": "La fin de pause doit etre differente du debut de pause."})

        if self.start_time and self.end_time and self.break_start_time and self.break_end_time:
            # Validation stricte uniquement pour les quarts dans la meme journee.
            if self.start_time <= self.end_time:
                if not (self.start_time <= self.break_start_time <= self.end_time):
                    raise ValidationError({"break_start_time": "Le debut de pause doit etre dans le quart de travail."})
                if not (self.start_time <= self.break_end_time <= self.end_time):
                    raise ValidationError({"break_end_time": "La fin de pause doit etre dans le quart de travail."})

    def save(self, *args, **kwargs):
        if not self.code:
            base = slugify(self.name or "")[:48] or "shift"
            candidate = base
            suffix = 1
            while WorkShift.objects.filter(tenant=self.tenant, code=candidate).exclude(pk=self.pk).exists():
                suffix += 1
                candidate = f"{base}-{suffix}"[:64]
            self.code = candidate
        self.full_clean()
        return super().save(*args, **kwargs)


class PlanningPeriod(models.Model):
    planning = models.ForeignKey(Planning, on_delete=models.CASCADE, related_name="periods")
    label = models.CharField(max_length=128, blank=True, default="")
    start_date = models.DateField()
    end_date = models.DateField()
    work_shifts = models.ManyToManyField(WorkShift, blank=True, related_name="planning_periods")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["planning", "label", "start_date", "end_date"],
                name="uq_planning_period_range",
            ),
        ]
        indexes = [
            models.Index(fields=["planning", "start_date", "end_date"]),
        ]

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError({"end_date": "La date de fin doit etre superieure ou egale a la date de debut."})

        overlapping_periods = (
            PlanningPeriod.objects.filter(
                planning=self.planning,
                start_date__lte=self.end_date,
                end_date__gte=self.start_date,
            )
            .exclude(pk=self.pk)
        )
        if overlapping_periods.exists():
            raise ValidationError({"start_date": "La periode se chevauche avec une autre periode du planning."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        label = self.label or self.planning.code
        return f"{label}:{self.start_date}->{self.end_date}"


class PlanningEntry(models.Model):
    DAY_CHOICES = PlanningDailySlot.DAY_CHOICES

    planning = models.ForeignKey(Planning, on_delete=models.CASCADE, related_name="entries")
    day_of_week = models.PositiveSmallIntegerField(choices=DAY_CHOICES, null=True, blank=True)
    sequence_index = models.PositiveIntegerField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    work_shift = models.ForeignKey(
        WorkShift,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="planning_entries",
    )
    is_rest_day = models.BooleanField(default=False)
    label = models.CharField(max_length=128, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["planning", "day_of_week"]),
            models.Index(fields=["planning", "sequence_index"]),
            models.Index(fields=["planning", "start_date", "end_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(day_of_week__isnull=False)
                | Q(sequence_index__isnull=False)
                | Q(start_date__isnull=False)
                | Q(end_date__isnull=False),
                name="ck_planning_entry_selector",
            ),
        ]

    def clean(self):
        if self.day_of_week is not None and (self.day_of_week < 0 or self.day_of_week > 6):
            raise ValidationError({"day_of_week": "Le jour doit etre compris entre 0 (lundi) et 6 (dimanche)."})
        if bool(self.start_date) != bool(self.end_date):
            raise ValidationError({"start_date": "start_date et end_date doivent etre renseignes ensemble."})
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "La date de fin doit etre superieure ou egale a la date de debut."})
        if self.is_rest_day and self.work_shift_id:
            raise ValidationError({"work_shift": "Un jour de repos ne peut pas avoir de work_shift."})
        if not self.is_rest_day and self.work_shift_id is None:
            raise ValidationError({"work_shift": "Le work_shift est obligatoire hors jour de repos."})
        if self.work_shift_id and self.work_shift.tenant_id != self.planning.tenant_id:
            raise ValidationError({"work_shift": "Le quart doit appartenir au meme tenant que le planning."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        selector = self.label or self.planning.code
        if self.start_date and self.end_date:
            return f"{selector}:{self.start_date}->{self.end_date}"
        if self.day_of_week is not None:
            return f"{selector}:dow={self.day_of_week}"
        return f"{selector}:seq={self.sequence_index}"


class PlanningAssignment(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="planning_assignments")
    planning = models.ForeignKey(
        Planning,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assignments",
    )
    work_shift = models.ForeignKey(
        WorkShift,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assignments",
    )
    department = models.ForeignKey(
        "Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="planning_assignments",
    )
    employee = models.ForeignKey(
        "Employee",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="planning_assignments",
    )
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    include_sub_departments = models.BooleanField(default=False)
    check_in_not_required = models.BooleanField(default=False)
    check_out_not_required = models.BooleanField(default=False)
    effective_for_holiday = models.BooleanField(default=True)
    effective_for_overtime = models.BooleanField(default=True)
    flexible_weekend = models.BooleanField(default=False)
    priority = models.IntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "valid_from", "valid_to"]),
            models.Index(fields=["tenant", "department", "valid_from"]),
            models.Index(fields=["tenant", "employee", "valid_from"]),
        ]

    def clean(self):
        if bool(self.department_id) == bool(self.employee_id):
            raise ValidationError({"department": "Renseigne soit department soit employee."})
        if not self.planning_id and not self.work_shift_id:
            raise ValidationError({"planning": "Au moins un planning ou un work_shift est requis."})
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValidationError({"valid_to": "La date de fin doit etre superieure ou egale a la date de debut."})
        if self.planning_id and self.planning.tenant_id != self.tenant_id:
            raise ValidationError({"planning": "Le planning doit appartenir au meme tenant."})
        if self.work_shift_id and self.work_shift.tenant_id != self.tenant_id:
            raise ValidationError({"work_shift": "Le quart doit appartenir au meme tenant."})
        if self.department_id and self.department.tenant_id != self.tenant_id:
            raise ValidationError({"department": "Le departement doit appartenir au meme tenant."})
        if self.employee_id and self.employee.tenant_id != self.tenant_id:
            raise ValidationError({"employee": "L'employee doit appartenir au meme tenant."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_temporary(self) -> bool:
        return self.valid_to is not None

    def is_active_on(self, target_date):
        if target_date < self.valid_from:
            return False
        if self.valid_to is not None and target_date > self.valid_to:
            return False
        return True

    def __str__(self) -> str:
        target = self.employee_id or self.department_id
        return f"{self.tenant.code}:{target}:{self.valid_from}->{self.valid_to or 'open'}"


class LeaveRequest(models.Model):
    TYPE_PAID = "paid"
    TYPE_SICK = "sick"
    TYPE_UNPAID = "unpaid"
    TYPE_SPECIAL = "special"
    TYPE_CHOICES = (
        (TYPE_PAID, "Paid"),
        (TYPE_SICK, "Sick"),
        (TYPE_UNPAID, "Unpaid"),
        (TYPE_SPECIAL, "Special"),
    )

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_CANCELLED, "Cancelled"),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="leave_requests")
    employee = models.ForeignKey("Employee", on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.CharField(max_length=16, choices=TYPE_CHOICES, default=TYPE_PAID)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True, default="")
    rejection_reason = models.TextField(blank=True, default="")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_leave_requests",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "employee", "start_date", "end_date"]),
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "leave_type"]),
        ]

    def clean(self):
        if self.employee_id and self.tenant_id and self.employee.tenant_id != self.tenant_id:
            raise ValidationError({"employee": "L'employee doit appartenir au meme tenant."})
        if self.end_date < self.start_date:
            raise ValidationError({"end_date": "La date de fin doit etre superieure ou egale a la date de debut."})
        if self.status == self.STATUS_APPROVED:
            if self.approved_by_id is None:
                raise ValidationError({"approved_by": "approved_by est obligatoire quand le conge est approuve."})
            if self.approved_at is None:
                raise ValidationError({"approved_at": "approved_at est obligatoire quand le conge est approuve."})
        if self.status != self.STATUS_APPROVED:
            self.approved_by = None
            self.approved_at = None
        if self.status != self.STATUS_REJECTED:
            self.rejection_reason = ""

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.tenant.code}:{self.employee_id}:{self.start_date}->{self.end_date}:{self.status}"


class Department(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="departments")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="departments")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    planning = models.ForeignKey(
        Planning,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_departments",
    )
    work_shift = models.ForeignKey(
        WorkShift,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_departments",
    )
    devices = models.ManyToManyField(Device, blank=True, related_name="departments")

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="uq_department_org_code"),
        ]
        indexes = [
            models.Index(fields=["tenant", "organization"]),
            models.Index(fields=["tenant", "parent"]),
        ]

    def clean(self):
        if self.organization_id and self.tenant_id and self.organization.tenant_id != self.tenant_id:
            raise ValidationError({"organization": "L'organisation doit appartenir au meme tenant."})

        if self.parent_id:
            if self.parent_id == self.id:
                raise ValidationError({"parent": "Un departement ne peut pas etre son propre parent."})
            if self.parent.organization_id != self.organization_id:
                raise ValidationError({"parent": "Le parent doit appartenir a la meme organisation."})
            if self.parent.tenant_id != self.tenant_id:
                raise ValidationError({"parent": "Le parent doit appartenir au meme tenant."})

            cursor = self.parent
            while cursor is not None:
                if cursor.id == self.id:
                    raise ValidationError({"parent": "Cycle detecte dans la hierarchie de departements."})
                cursor = cursor.parent

        if self.planning_id and self.planning.tenant_id != self.tenant_id:
            raise ValidationError({"planning": "Le planning doit appartenir au meme tenant."})
        if self.work_shift_id and self.work_shift.tenant_id != self.tenant_id:
            raise ValidationError({"work_shift": "Le quart de travail doit appartenir au meme tenant."})

    def save(self, *args, **kwargs):
        if not self.code:
            from django.utils.text import slugify
            base = slugify(self.name or "")[:48] or "dept"
            candidate = base
            suffix = 1
            while Department.objects.filter(organization=self.organization, code=candidate).exclude(pk=self.pk).exists():
                suffix += 1
                candidate = f"{base}-{suffix}"[:64]
            self.code = candidate
        self.full_clean()
        return super().save(*args, **kwargs)

    def get_ancestors(self):
        ancestors = []
        node = self.parent
        while node is not None:
            ancestors.append(node)
            node = node.parent
        return ancestors

    def get_effective_planning(self):
        node = self
        while node is not None:
            if node.planning_id:
                return node.planning
            node = node.parent
        return None

    def get_effective_work_shift(self):
        node = self
        while node is not None:
            if node.work_shift_id:
                return node.work_shift
            node = node.parent
        return None

    def get_effective_devices(self, include_ancestors: bool = False):
        if not include_ancestors:
            return list(self.devices.order_by("id"))

        devices_by_id = {}
        node = self
        while node is not None:
            for device in node.devices.order_by("id"):
                devices_by_id.setdefault(device.id, device)
            node = node.parent
        return list(devices_by_id.values())

    def __str__(self) -> str:
        return f"{self.organization.code}:{self.name}"


class Employee(models.Model):
    DEVICE_ASSIGNMENT_EMPLOYEE_ONLY = "employee_only"
    DEVICE_ASSIGNMENT_DEPARTMENT_ONLY = "department_only"
    DEVICE_ASSIGNMENT_COMBINED = "combined"
    DEVICE_ASSIGNMENT_MODE_CHOICES = (
        (DEVICE_ASSIGNMENT_EMPLOYEE_ONLY, "Employee only"),
        (DEVICE_ASSIGNMENT_DEPARTMENT_ONLY, "Department only"),
        (DEVICE_ASSIGNMENT_COMBINED, "Combined"),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="employees")
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        related_name="employees",
        null=True,
        blank=True,
    )
    planning = models.ForeignKey(
        Planning,
        on_delete=models.SET_NULL,
        related_name="assigned_employees",
        null=True,
        blank=True,
    )
    work_shift = models.ForeignKey(
        WorkShift,
        on_delete=models.SET_NULL,
        related_name="assigned_employees",
        null=True,
        blank=True,
    )
    work_shifts = models.ManyToManyField(
        WorkShift,
        blank=True,
        related_name="employees",
    )
    devices = models.ManyToManyField(Device, blank=True, related_name="employees")
    device_assignment_mode = models.CharField(
        max_length=24,
        choices=DEVICE_ASSIGNMENT_MODE_CHOICES,
        default=DEVICE_ASSIGNMENT_COMBINED,
    )
    access_groups = models.ManyToManyField("AccessGroup", blank=True, related_name="employees")

    employee_no = models.CharField(max_length=128)
    name = models.CharField(max_length=255, default="")
    first_name = models.CharField(max_length=100, blank=True, default="")
    last_name = models.CharField(max_length=100, blank=True, default="")
    gender = models.CharField(max_length=16, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=64, blank=True, default="")
    remark = models.TextField(blank=True, default="")

    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    access_group = models.CharField(max_length=128, blank=True, default="")
    pin_code = models.CharField(max_length=32, blank=True, default="")
    is_super_user = models.BooleanField(default=False)
    extended_door_open_time = models.PositiveIntegerField(null=True, blank=True)
    is_blocklisted = models.BooleanField(default=False)
    is_visitor = models.BooleanField(default=False)
    is_device_operator = models.BooleanField(default=False)
    custom_profile = models.CharField(max_length=128, blank=True, default="")
    only_authenticate = models.BooleanField(default=False)

    date_of_birth = models.DateField(null=True, blank=True)
    identity_type = models.CharField(max_length=64, blank=True, default="")
    identity_no = models.CharField(max_length=128, blank=True, default="")
    position = models.CharField(max_length=128, blank=True, default="")
    hire_date = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True, default="")
    needs_gateway_push = models.BooleanField(default=True)
    last_gateway_push_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "employee_no"], name="uq_employee_tenant_employee_no"),
        ]
        indexes = [
            models.Index(fields=["tenant", "employee_no"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["tenant", "needs_gateway_push"]),
        ]

    def clean(self):
        if self.department_id and self.department.tenant_id != self.tenant_id:
            raise ValidationError({"department": "Le departement doit appartenir au meme tenant."})
        if self.planning_id and self.planning.tenant_id != self.tenant_id:
            raise ValidationError({"planning": "Le planning doit appartenir au meme tenant."})
        if self.work_shift_id and self.work_shift.tenant_id != self.tenant_id:
            raise ValidationError({"work_shift": "Le quart de travail doit appartenir au meme tenant."})
        if self.pk:
            invalid_multi_shift_ids = [
                shift.id
                for shift in self.work_shifts.all()
                if shift.tenant_id != self.tenant_id
            ]
            if invalid_multi_shift_ids:
                raise ValidationError({"work_shifts": f"Quarts hors tenant: {invalid_multi_shift_ids}"})

    @property
    def full_name(self) -> str:
        if self.name:
            return self.name
        return " ".join([part for part in [self.first_name, self.last_name] if part]).strip()

    def __str__(self) -> str:
        return f"{self.employee_no} ({self.full_name or 'No name'})"

    def get_effective_devices(
        self,
        include_department_ancestors: bool = True,
        include_access_group_readers: bool = True,
    ):
        include_employee_devices = self.device_assignment_mode in {
            self.DEVICE_ASSIGNMENT_EMPLOYEE_ONLY,
            self.DEVICE_ASSIGNMENT_COMBINED,
        }
        include_department_devices = self.device_assignment_mode in {
            self.DEVICE_ASSIGNMENT_DEPARTMENT_ONLY,
            self.DEVICE_ASSIGNMENT_COMBINED,
        }

        devices_by_id = {}
        if include_employee_devices:
            for device in self.devices.order_by("id"):
                devices_by_id.setdefault(device.id, device)

        if include_department_devices and self.department_id:
            for device in self.department.get_effective_devices(include_ancestors=include_department_ancestors):
                devices_by_id.setdefault(device.id, device)

        if include_access_group_readers:
            for access_group in self.access_groups.all():
                for device in access_group.readers.order_by("id"):
                    devices_by_id.setdefault(device.id, device)

        return list(devices_by_id.values())

    @property
    def effective_planning(self):
        from employees.schedule_resolver import ScheduleResolver

        return ScheduleResolver().resolve_effective_planning(self)

    @property
    def effective_work_shift(self):
        from employees.schedule_resolver import ScheduleResolver

        return ScheduleResolver().resolve_effective_work_shift(self)

    @property
    def effective_work_shifts(self):
        from employees.schedule_resolver import ScheduleResolver

        return ScheduleResolver().resolve_effective_work_shifts(self)


class EmployeeAttribute(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="attributes")
    name = models.CharField(max_length=64)
    value = models.TextField(default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["employee", "name"], name="uq_employee_attribute_employee_name"),
        ]
        indexes = [
            models.Index(fields=["name"]),
        ]

    def __str__(self) -> str:
        return f"{self.employee.employee_no}:{self.name}"


class EmployeeCard(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="cards")
    card_no = models.CharField(max_length=128)
    card_type = models.CharField(max_length=64, default="normalCard")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["employee", "card_no"], name="uq_employee_card_no"),
        ]
        indexes = [
            models.Index(fields=["card_no"]),
        ]

    def __str__(self) -> str:
        return f"{self.employee.employee_no}:{self.card_no}"


class EmployeeFingerprint(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="fingerprints")
    finger_index = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(10)])
    template = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["employee", "finger_index"], name="uq_employee_fingerprint_slot"),
        ]
        indexes = [
            models.Index(fields=["finger_index"]),
        ]

    def __str__(self) -> str:
        return f"{self.employee.employee_no}:F{self.finger_index}"


class EmployeeFace(models.Model):
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name="face")
    face_data = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.employee.employee_no}:face"


class AccessGroup(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="access_groups")
    planning = models.ForeignKey(
        Planning,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="access_groups",
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=64, blank=True, default="")
    description = models.TextField(blank=True, default="")
    readers = models.ManyToManyField(Device, blank=True, related_name="access_groups")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uq_access_group_tenant_name"),
            models.UniqueConstraint(fields=["tenant", "code"], name="uq_access_group_tenant_code"),
        ]
        indexes = [
            models.Index(fields=["tenant", "name"]),
        ]

    def clean(self):
        if self.planning_id and self.planning.tenant_id != self.tenant_id:
            raise ValidationError({"planning": "Le planning doit appartenir au meme tenant."})

    def save(self, *args, **kwargs):
        if not self.code:
            base = slugify(self.name or "")[:48] or "group"
            candidate = base
            suffix = 1
            while AccessGroup.objects.filter(tenant=self.tenant, code=candidate).exclude(pk=self.pk).exists():
                suffix += 1
                candidate = f"{base}-{suffix}"[:64]
            self.code = candidate
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.tenant.code}:{self.name}"
