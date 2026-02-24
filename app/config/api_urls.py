from django.urls import path, include
from rest_framework.routers import DefaultRouter
from tenants.views import TenantViewSet
from devices.views import DeviceViewSet
from events.views import AttendanceEventViewSet

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

router = DefaultRouter()
router.register(r'tenants', TenantViewSet)
router.register(r'devices', DeviceViewSet)
router.register(r'events', AttendanceEventViewSet)

urlpatterns = [
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('', include(router.urls)),
]
