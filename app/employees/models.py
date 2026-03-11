from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

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

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=64)
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

    def save(self, *args, **kwargs):
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

    def __str__(self) -> str:
        return f"{self.organization.code}:{self.name}"


class Employee(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="employees")
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        related_name="employees",
        null=True,
        blank=True,
    )
    devices = models.ManyToManyField(Device, blank=True, related_name="employees")

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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "employee_no"], name="uq_employee_tenant_employee_no"),
        ]
        indexes = [
            models.Index(fields=["tenant", "employee_no"]),
            models.Index(fields=["is_active"]),
        ]

    def clean(self):
        if self.department_id and self.department.tenant_id != self.tenant_id:
            raise ValidationError({"department": "Le departement doit appartenir au meme tenant."})

    @property
    def full_name(self) -> str:
        if self.name:
            return self.name
        return " ".join([part for part in [self.first_name, self.last_name] if part]).strip()

    def __str__(self) -> str:
        return f"{self.employee_no} ({self.full_name or 'No name'})"

    @property
    def effective_planning(self):
        if self.department_id is None:
            return None
        return self.department.get_effective_planning()


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
