from django.db import models
from django.contrib.auth import get_user_model
from tenants.models import Tenant


User = get_user_model()


ISUP_PORT_CHOICES = (
    (7660, '7660'),
    (7661, '7661'),
)

class Device(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='devices', null=True, blank=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)

    ip_address = models.GenericIPAddressField(default='213.156.133.202', editable=False)
    port = models.PositiveIntegerField(choices=ISUP_PORT_CHOICES, default=7661)
    serial_number = models.CharField(max_length=9, blank=True, default='')

    dev_index = models.CharField(max_length=64, unique=True)

    device_id = models.CharField(max_length=100, blank=True, default='')
    name = models.CharField(max_length=255, blank=True, default='')
    model = models.CharField(max_length=100, blank=True, default='')
    protocol = models.CharField(max_length=50, blank=True, default='')
    status = models.CharField(max_length=30, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name or self.device_id or self.dev_index
