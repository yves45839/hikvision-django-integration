from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets

from tenants.models import Tenant
from tenants.serializers import TenantSerializer
from tenants.services import get_admin_tenant_ids


class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all().order_by("-id")
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_superuser or user.is_staff:
            return queryset
        return queryset.filter(id__in=get_admin_tenant_ids(user))
