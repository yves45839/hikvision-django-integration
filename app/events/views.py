from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from tenants.services import scope_queryset_to_user_tenants

from .models import AttendanceEvent
from .serializers import AttendanceEventSerializer


class AttendanceEventViewSet(viewsets.ModelViewSet):
    queryset = AttendanceEvent.objects.none()
    serializer_class = AttendanceEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = AttendanceEvent.objects.all().order_by("-id")
        queryset = scope_queryset_to_user_tenants(queryset, self.request.user, tenant_field="tenant_id")
        user = self.request.user
        if user.is_superuser or user.is_staff:
            return queryset
        return queryset.filter(device__owner=user)
