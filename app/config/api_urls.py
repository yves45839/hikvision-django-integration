from django.urls import path, include
from rest_framework.routers import DefaultRouter
from tenants.views import TenantViewSet
from devices.views import DeviceViewSet
from events.views import AttendanceEventViewSet
from employees.views import DepartmentViewSet, EmployeeViewSet, OrganizationViewSet, PlanningViewSet

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

router = DefaultRouter()
router.register(r'tenants', TenantViewSet)
router.register(r'devices', DeviceViewSet)
router.register(r'events', AttendanceEventViewSet)
router.register(r'employees', EmployeeViewSet)
router.register(r'organizations', OrganizationViewSet)
router.register(r'departments', DepartmentViewSet)
router.register(r'plannings', PlanningViewSet)

urlpatterns = [
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('', include('hik_gateway.urls')),
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('', include(router.urls)),
]
