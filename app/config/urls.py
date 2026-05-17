from django.contrib import admin
from django.urls import path, include
from config.health_views import health_check, readiness_check
from config.legal_views import terms_of_service, privacy_policy

urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('ready/', readiness_check, name='readiness_check'),
    path('legal/tos/', terms_of_service, name='legal-tos'),
    path('legal/privacy/', privacy_policy, name='legal-privacy'),
    path('api/', include('config.api_urls')),
    path('i18n/', include('django.conf.urls.i18n')),
    path('admin/', admin.site.urls),
]
