from django.urls import path

from hik_gateway.views import hik_devices_api, hik_devices_page, hik_event_webhook, hikdevice_devices_space

urlpatterns = [
    path("hikgateway/devices/", hik_devices_api, name="hikgateway-devices-api"),
    path("hik/devices", hik_devices_page, name="hik-devices"),
    path("hikdevice/devices", hikdevice_devices_space, name="hikdevice-devices-space"),
    path("hik/events", hik_event_webhook, name="hik-events"),
    path("hikvision/events", hik_event_webhook, name="hikvision-events"),
]
