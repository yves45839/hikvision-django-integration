from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """0.5: Audit log for tracking user actions and changes."""
    
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_events_as_actor'
    )
    action = models.CharField(max_length=100)
    target_model = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    tenant_code = models.CharField(max_length=100, blank=True, db_index=True)
    extra = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['tenant_code', 'created_at']),
            models.Index(fields=['actor', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.actor}:{self.action}:{self.target_model}:{self.target_id}"
