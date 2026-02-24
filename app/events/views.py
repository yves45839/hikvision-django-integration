from rest_framework import viewsets
from .models import AttendanceEvent
from .serializers import AttendanceEventSerializer

class AttendanceEventViewSet(viewsets.ModelViewSet):
    queryset = AttendanceEvent.objects.all().order_by('-id')
    serializer_class = AttendanceEventSerializer
