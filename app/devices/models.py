from django.db import models
from tenants.models import Tenant

class Device(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)

    dev_index = models.CharField(max_length=64, unique=True)

    device_id = models.CharField(max_length=100, blank=True, default='')
    name = models.CharField(max_length=255, blank=True, default='')
    model = models.CharField(max_length=100, blank=True, default='')
    protocol = models.CharField(max_length=50, blank=True, default='')
    status = models.CharField(max_length=30, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name or self.device_id or self.dev_index
