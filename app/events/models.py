from django.db import models
from tenants.models import Tenant
from devices.models import Device

class AttendanceEvent(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    user_id = models.CharField(max_length=100)
    timestamp = models.DateTimeField()
    event_type = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
