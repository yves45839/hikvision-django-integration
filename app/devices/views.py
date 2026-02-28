from rest_framework import viewsets
from .models import Device
from .serializers import DeviceSerializer


class DeviceViewSet(viewsets.ModelViewSet):
    queryset = Device.objects.none()
    serializer_class = DeviceSerializer

    def get_queryset(self):
        queryset = Device.objects.all().order_by('-id')
        owner_only = str(self.request.query_params.get('owner_only', '')).lower() in {'1', 'true', 'yes'}

        if owner_only and self.request.user.is_authenticated:
            return queryset.filter(owner=self.request.user)

        return queryset
