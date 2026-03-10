from django.urls import path

from hik_gateway.views import (
    hik_acs_events_api,
    hik_catchup_acs_events_api,
    hik_devices_api,
    hik_devices_page,
    hik_events_api,
    hik_event_webhook,
    hik_register_webhooks_api,
    hik_sync_devices_api,
    hikdevice_devices_space,
)

urlpatterns = [
    path("hikgateway/devices/", hik_devices_api, name="hikgateway-devices-api"),
    path("hikgateway/sync-devices/", hik_sync_devices_api, name="hikgateway-sync-devices-api"),
    path("hikgateway/acs-events/", hik_acs_events_api, name="hikgateway-acs-events-api"),
    path("hikgateway/events/", hik_events_api, name="hikgateway-events-api"),
    path("hikgateway/catchup-acs-events/", hik_catchup_acs_events_api, name="hikgateway-catchup-acs-events-api"),
    path("hikgateway/register-webhooks/", hik_register_webhooks_api, name="hikgateway-register-webhooks-api"),
    path("hik/devices", hik_devices_page, name="hik-devices"),
    path("hikdevice/devices", hikdevice_devices_space, name="hikdevice-devices-space"),
    path("hik/events", hik_event_webhook, name="hik-events"),
    path("hikvision/events", hik_event_webhook, name="hikvision-events"),
]
