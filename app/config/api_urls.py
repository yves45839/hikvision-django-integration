from django.urls import path, include
from rest_framework.routers import DefaultRouter
from tenants.views import TenantViewSet
from devices.views import DeviceOnboardingJobViewSet, DeviceViewSet
from events.views import AttendanceEventViewSet
from employees.views import (
    AccessGroupViewSet,
    DepartmentViewSet,
    EmployeeViewSet,
    LeaveRequestViewSet,
    OrganizationViewSet,
    PlanningAssignmentViewSet,
    PlanningViewSet,
    WorkShiftViewSet,
)

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from presence.views import SiteViewSet
from config.home_views import home_summary_api
from config.beta_views import beta_info

router = DefaultRouter()
router.register(r'tenants', TenantViewSet)
router.register(r'devices', DeviceViewSet)
router.register(r'device-onboarding-jobs', DeviceOnboardingJobViewSet, basename='device-onboarding-jobs')
router.register(r'events', AttendanceEventViewSet)
router.register(r'employees', EmployeeViewSet)
router.register(r'organizations', OrganizationViewSet)
router.register(r'departments', DepartmentViewSet)
router.register(r'plannings', PlanningViewSet)
router.register(r'planning-assignments', PlanningAssignmentViewSet)
router.register(r'work-shifts', WorkShiftViewSet)
router.register(r'access-groups', AccessGroupViewSet)
router.register(r'leave-requests', LeaveRequestViewSet)
router.register(r'punch-sites', SiteViewSet)

urlpatterns = [
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('', include('tenants.auth_urls')),
    path('', include('hik_gateway.urls')),
    path('', include('audit.urls')),
    path('', include('presence.urls')),
    path('billing/', include('billing.urls')),
    path('home/summary/', home_summary_api, name='home-summary-api'),
    path('beta/info/', beta_info, name='beta-info'),
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('', include(router.urls)),
]
