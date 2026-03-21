from rest_framework import serializers
from .models import Tenant


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = [
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
        ]
