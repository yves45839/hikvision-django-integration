from django.urls import path

from hik_gateway.views import hik_devices_page, hik_event_webhook

urlpatterns = [
    path("hik/devices", hik_devices_page, name="hik-devices"),
    path("hik/events", hik_event_webhook, name="hik-events"),
    path("hikvision/events", hik_event_webhook, name="hikvision-events"),
]
