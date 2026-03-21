from django.contrib import admin

from devices.models import Device, DeviceOnboardingJob, DeviceOrganizationBinding


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "dev_index", "serial_number", "name", "status", "created_at")
    list_filter = ("tenant", "status", "protocol")
    search_fields = ("dev_index", "serial_number", "name")


@admin.register(DeviceOrganizationBinding)
class DeviceOrganizationBindingAdmin(admin.ModelAdmin):
    list_display = ("id", "device", "organization", "is_primary", "assigned_by", "created_at")
    list_filter = ("organization__tenant", "is_primary")
    search_fields = ("device__dev_index", "device__serial_number", "organization__name", "organization__code")


@admin.register(DeviceOnboardingJob)
class DeviceOnboardingJobAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "organization", "sn", "status", "review_reason", "requested_by", "created_at")
    list_filter = ("status", "review_reason", "tenant")
    search_fields = ("sn", "dev_name", "tenant__code")
