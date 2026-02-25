from rest_framework import viewsets
from .models import AttendanceEvent
from .serializers import AttendanceEventSerializer

class AttendanceEventViewSet(viewsets.ModelViewSet):
    queryset = AttendanceEvent.objects.none()
    serializer_class = AttendanceEventSerializer

    def get_queryset(self):
        return AttendanceEvent.objects.filter(device__owner=self.request.user).order_by('-id')
