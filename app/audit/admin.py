from django.contrib import admin
from audit.models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'actor', 'action', 'target_model', 'tenant_code', 'created_at')
    list_filter = ('action', 'tenant_code', 'created_at')
    search_fields = ('actor__email', 'target_id', 'tenant_code')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'actor', 'action', 'target_model', 'target_id', 'ip_address', 'tenant_code', 'extra')
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
