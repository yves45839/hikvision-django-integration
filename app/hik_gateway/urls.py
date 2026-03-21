from django.urls import path

from hik_gateway.views import (
    hik_acs_events_api,
    hik_attendance_corrections_api,
    hik_attendance_correction_logs_api,
    hik_attendance_reports_api,
    hik_catchup_acs_events_api,
    hik_devices_api,
    hik_devices_page,
    hik_events_api,
    hik_event_webhook,
    hik_read_card_api,
    hik_register_webhooks_api,
    hik_sync_devices_api,
    hikdevice_devices_space,
)

urlpatterns = [
    path("hikgateway/devices/", hik_devices_api, name="hikgateway-devices-api"),
    path("hikgateway/reports/attendance/", hik_attendance_reports_api, name="hikgateway-attendance-reports-api"),
    path("hikgateway/attendance-corrections/", hik_attendance_corrections_api, name="hikgateway-attendance-corrections-api"),
    path("hikgateway/attendance-corrections/logs/", hik_attendance_correction_logs_api, name="hikgateway-attendance-correction-logs-api"),
    path("hikgateway/sync-devices/", hik_sync_devices_api, name="hikgateway-sync-devices-api"),
    path("hikgateway/acs-events/", hik_acs_events_api, name="hikgateway-acs-events-api"),
    path("hikgateway/read-card/", hik_read_card_api, name="hikgateway-read-card-api"),
    path("hikgateway/events/", hik_events_api, name="hikgateway-events-api"),
    path("hikgateway/catchup-acs-events/", hik_catchup_acs_events_api, name="hikgateway-catchup-acs-events-api"),
    path("hikgateway/register-webhooks/", hik_register_webhooks_api, name="hikgateway-register-webhooks-api"),
    path("hik/devices", hik_devices_page, name="hik-devices"),
    path("hikdevice/devices", hikdevice_devices_space, name="hikdevice-devices-space"),
    path("hik/events", hik_event_webhook, name="hik-events"),
    path("hikvision/events", hik_event_webhook, name="hikvision-events"),
]
