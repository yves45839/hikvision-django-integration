from django.contrib import admin

from tenants.models import EmailVerificationToken, Tenant, TenantMembership


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
    list_display = ("id", "tenant", "user", "token", "is_used", "expires_at", "created_at", "used_at")
    list_filter = ("is_used", "tenant")
    search_fields = ("tenant__code", "user__username", "user__email", "token")
