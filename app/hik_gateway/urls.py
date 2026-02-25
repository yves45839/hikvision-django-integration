from django.urls import path

from hik_gateway.views import hik_event_webhook

urlpatterns = [
    path("hikvision/events", hik_event_webhook, name="hikvision-events"),
]
