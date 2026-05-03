from django.contrib import admin

from employees.models import (
    Department,
    Employee,
    EmployeeAttribute,
    EmployeeCard,
    EmployeeFace,
    EmployeeFingerprint,
    LeaveRequest,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    Planning,
    PlanningAssignment,
    PlanningEntry,
    WorkShift,
)


class EmployeeAttributeInline(admin.TabularInline):
    model = EmployeeAttribute
    extra = 0


class EmployeeCardInline(admin.TabularInline):
    model = EmployeeCard
    extra = 0


class EmployeeFingerprintInline(admin.TabularInline):
    model = EmployeeFingerprint
    extra = 0


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "department",
        "device_assignment_mode",
        "device_names",
        "work_shift",
        "work_shift_names",
        "employee_no",
        "name",
        "is_active",
        "created_at",
    )
    list_filter = ("tenant", "department", "device_assignment_mode", "work_shift", "work_shifts", "is_active")
    search_fields = ("employee_no", "name", "first_name", "last_name", "email", "phone")
    filter_horizontal = ("devices", "access_groups", "work_shifts")
    inlines = [EmployeeAttributeInline, EmployeeCardInline, EmployeeFingerprintInline]

    @staticmethod
    def work_shift_names(obj):
        return ", ".join(obj.work_shifts.order_by("name").values_list("name", flat=True))

    @staticmethod
    def device_names(obj):
        return ", ".join(
            obj.devices.order_by("name", "dev_index").values_list("name", flat=True)
        ) or ", ".join(obj.devices.order_by("dev_index").values_list("dev_index", flat=True))


@admin.register(EmployeeAttribute)
class EmployeeAttributeAdmin(admin.ModelAdmin):
    list_display = ("id", "employee", "name", "value", "created_at")
    list_filter = ("name",)
    search_fields = ("employee__employee_no", "name", "value")


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "name", "code", "created_at")
    list_filter = ("tenant",)
    search_fields = ("name", "code")


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "user", "role", "created_at")
    list_filter = ("role", "organization__tenant")
    search_fields = ("organization__name", "organization__code", "user__username", "user__email")


@admin.register(OrganizationInvitation)
class OrganizationInvitationAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "organization", "email", "role", "status", "expires_at", "created_at")
    list_filter = ("status", "role", "tenant")
    search_fields = ("email", "organization__name", "organization__code", "token")


@admin.register(Planning)
class PlanningAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "name", "code", "timezone", "created_at")
    list_filter = ("tenant", "timezone")
    search_fields = ("name", "code")


@admin.register(PlanningEntry)
class PlanningEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "planning", "day_of_week", "sequence_index", "start_date", "end_date", "work_shift", "is_rest_day")
    list_filter = ("planning__tenant", "day_of_week", "is_rest_day")
    search_fields = ("planning__name", "label", "work_shift__name")


@admin.register(PlanningAssignment)
class PlanningAssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "planning", "work_shift", "department", "employee", "valid_from", "valid_to", "priority")
    list_filter = ("tenant", "include_sub_departments", "effective_for_holiday", "effective_for_overtime")
    search_fields = ("planning__name", "work_shift__name", "department__name", "employee__employee_no", "employee__name")


@admin.register(WorkShift)
class WorkShiftAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "name", "code", "start_time", "end_time", "created_at")
    list_filter = ("tenant",)
    search_fields = ("name", "code")


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "employee", "leave_type", "status", "start_date", "end_date", "approved_by", "created_at")
    list_filter = ("tenant", "leave_type", "status")
    search_fields = ("employee__employee_no", "employee__name", "reason", "rejection_reason")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "organization", "parent", "planning", "work_shift", "name", "code", "created_at")
    list_filter = ("tenant", "organization")
    search_fields = ("name", "code")
    filter_horizontal = ("devices",)


@admin.register(EmployeeFace)
class EmployeeFaceAdmin(admin.ModelAdmin):
    list_display = ("id", "employee", "created_at")
    search_fields = ("employee__employee_no", "employee__name")
