from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets

from tenants.models import Tenant, TenantMembership
from tenants.serializers import TenantSerializer


class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all().order_by("-id")
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_superuser or user.is_staff:
            return queryset
        tenant_ids = TenantMembership.objects.filter(user=user).values_list("tenant_id", flat=True)
        return queryset.filter(id__in=tenant_ids)
