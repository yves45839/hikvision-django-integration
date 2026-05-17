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
        # Scoping tenant : un utilisateur ne voit que les events des tenants
        # dont il est membre (BACKLOG 4.5). Les superusers/staff voient tout.
        queryset = AttendanceEvent.objects.all().order_by("-id")
        return scope_queryset_to_user_tenants(
            queryset, self.request.user, tenant_field="tenant_id"
        )
