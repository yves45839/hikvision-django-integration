from django.contrib import admin

from employees.models import (
    Department,
    Employee,
    EmployeeAttribute,
    EmployeeCard,
    EmployeeFace,
    EmployeeFingerprint,
    Organization,
    Planning,
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
    list_display = ("id", "tenant", "department", "employee_no", "name", "is_active", "created_at")
    list_filter = ("tenant", "department", "is_active")
    search_fields = ("employee_no", "name", "first_name", "last_name", "email", "phone")
    inlines = [EmployeeAttributeInline, EmployeeCardInline, EmployeeFingerprintInline]


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


@admin.register(Planning)
class PlanningAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "name", "code", "timezone", "created_at")
    list_filter = ("tenant", "timezone")
    search_fields = ("name", "code")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "organization", "parent", "planning", "name", "code", "created_at")
    list_filter = ("tenant", "organization")
    search_fields = ("name", "code")


@admin.register(EmployeeFace)
class EmployeeFaceAdmin(admin.ModelAdmin):
    list_display = ("id", "employee", "created_at")
    search_fields = ("employee__employee_no", "employee__name")
