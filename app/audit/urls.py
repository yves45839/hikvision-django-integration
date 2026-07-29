from django.urls import path

from audit.views import audit_events_api

urlpatterns = [
    path("audit/events/", audit_events_api, name="audit-events-api"),
]
