from rest_framework import viewsets
from .models import Device
from .serializers import DeviceSerializer


class DeviceViewSet(viewsets.ModelViewSet):
    queryset = Device.objects.none()
    serializer_class = DeviceSerializer

    def get_queryset(self):
        return Device.objects.filter(owner=self.request.user).order_by('-id')
