from rest_framework import viewsets
from .models import Tenant
from .serializers import TenantSerializer

class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all().order_by('-id')
    serializer_class = TenantSerializer
