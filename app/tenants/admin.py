from django.contrib import admin

from tenants.models import (
    EmailVerificationToken,
    OrganizationCustomRole,
    OrganizationCustomRoleAssignment,
    PasswordResetToken,
    Tenant,
    TenantMembership,
)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "code",
        "domain",
        "is_domain_verified",
        "is_active",
        "device_quota",
        "payment_status",
        "requires_manual_review",
        "created_at",
    )
    search_fields = ("name", "code", "domain")
    list_filter = ("is_active", "is_domain_verified", "payment_status", "requires_manual_review")


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "user", "role", "is_primary", "created_at")
    list_filter = ("role", "is_primary")
    search_fields = ("tenant__code", "user__username", "user__email")


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "user", "token", "otp_code", "is_used", "expires_at", "created_at", "used_at")
    list_filter = ("is_used", "tenant")
    search_fields = ("tenant__code", "user__username", "user__email", "token", "otp_code")


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "user", "token", "otp_code", "is_used", "expires_at", "created_at", "used_at")
    list_filter = ("is_used", "tenant")
    search_fields = ("user__username", "user__email", "token", "otp_code")


@admin.register(OrganizationCustomRole)
class OrganizationCustomRoleAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "organization", "name", "is_active", "created_by", "created_at")
    list_filter = ("tenant", "organization", "is_active")
    search_fields = ("name", "description", "organization__name", "tenant__code")


@admin.register(OrganizationCustomRoleAssignment)
class OrganizationCustomRoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "organization", "role", "user", "assigned_by", "created_at")
    list_filter = ("tenant", "organization", "role")
    search_fields = ("organization__name", "role__name", "user__username", "user__email")
