from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework import status
from rest_framework.test import APITestCase

from hik_gateway.models import AttendanceLog, Device, Gateway, RawEvent
from tenants.models import Tenant


class HikWebhookTenantRoutingTests(APITestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Tenant A", code="tenant-a")
        self.tenant_b = Tenant.objects.create(name="Tenant B", code="tenant-b")

        self.gateway_a = Gateway.objects.create(
            tenant=self.tenant_a,
            base_url="https://gw-a.local",
            username="admin",
            password="pass",
        )
        self.gateway_b = Gateway.objects.create(
            tenant=self.tenant_b,
            base_url="https://gw-b.local",
            username="admin",
            password="pass",
        )

        self.device_a = Device.objects.create(
            gateway=self.gateway_a,
            tenant=self.tenant_a,
            serial_number="SN-A",
            dev_index="shared-dev-index",
            status="online",
        )
        self.device_b = Device.objects.create(
            gateway=self.gateway_b,
            tenant=self.tenant_b,
            serial_number="SN-B",
            dev_index="shared-dev-index",
            status="online",
        )

    def test_webhook_routes_event_to_devices_of_given_tenant(self):
        payload = {
            "EventNotificationAlert": {
                "eventType": "AccessControllerEvent",
                "devIndex": "shared-dev-index",
                "dateTime": "2026-02-01T08:00:00Z",
                "AccessControllerEvent": {
                    "attendanceStatus": "checkin",
                    "employeeNoString": "E1001",
                    "serialNo": "100",
                    "subEventType": 1,
                },
            }
        }

        response = self.client.post(
            "/api/hikvision/events",
            payload,
            format="json",
            HTTP_X_TENANT_CODE="tenant-b",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(RawEvent.objects.count(), 1)
        self.assertEqual(AttendanceLog.objects.count(), 1)

        raw_event = RawEvent.objects.get()
        attendance = AttendanceLog.objects.get()

        self.assertEqual(raw_event.tenant, self.tenant_b)
        self.assertEqual(raw_event.device, self.device_b)
        self.assertEqual(attendance.tenant, self.tenant_b)
        self.assertEqual(attendance.device, self.device_b)


    def test_webhook_accepts_short_hik_events_endpoint(self):
        payload = {
            "EventNotificationAlert": {
                "eventType": "AccessControllerEvent",
                "devIndex": "shared-dev-index",
                "dateTime": "2026-02-01T08:00:00Z",
                "AccessControllerEvent": {
                    "attendanceStatus": "checkin",
                    "employeeNoString": "E1002",
                    "serialNo": "101",
                    "subEventType": 1,
                },
            }
        }

        response = self.client.post(
            "/api/hik/events",
            payload,
            format="json",
            HTTP_X_TENANT_CODE="tenant-a",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(RawEvent.objects.count(), 1)
        self.assertEqual(AttendanceLog.objects.count(), 1)

    def test_webhook_rejects_unknown_tenant_code(self):
        payload = {
            "EventNotificationAlert": {
                "eventType": "AccessControllerEvent",
                "devIndex": "shared-dev-index",
                "dateTime": "2026-02-01T08:00:00Z",
                "AccessControllerEvent": {
                    "attendanceStatus": "checkin",
                    "employeeNoString": "E1001",
                    "serialNo": "100",
                    "subEventType": 1,
                },
            }
        }

        response = self.client.post(
            "/api/hikvision/events",
            payload,
            format="json",
            HTTP_X_TENANT_CODE="tenant-inconnu",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["detail"], "Unknown tenant")
        self.assertEqual(RawEvent.objects.count(), 0)
        self.assertEqual(AttendanceLog.objects.count(), 0)


class HikCheckDeviceCommandTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant Cmd", code="tenant-cmd")
        self.gateway = Gateway.objects.create(
            tenant=self.tenant,
            base_url="https://gw.local",
            username="admin",
            password="pass",
        )

    @patch("hik_gateway.management.commands.hik_check_device.HikGatewayClient.device_list")
    def test_command_returns_success_when_device_is_found(self, mock_device_list):
        mock_device_list.return_value = {
            "DeviceList": {
                "Device": [
                    {
                        "serialNumber": "SN-FOUND",
                        "devIndex": "IDX-001",
                        "status": "online",
                    }
                ]
            }
        }

        stdout = StringIO()
        call_command(
            "hik_check_device",
            "--tenant",
            "tenant-cmd",
            "--serial",
            "SN-FOUND",
            stdout=stdout,
        )

        self.assertIn("Communication OK", stdout.getvalue())
        mock_device_list.assert_called_once()

    @patch("hik_gateway.management.commands.hik_check_device.HikGatewayClient.device_list")
    def test_command_raises_error_when_device_is_missing(self, mock_device_list):
        mock_device_list.return_value = {"DeviceList": {"Device": []}}

        with self.assertRaises(CommandError) as exc:
            call_command(
                "hik_check_device",
                "--tenant",
                "tenant-cmd",
                "--serial",
                "SN-UNKNOWN",
            )

        self.assertIn("Device introuvable", str(exc.exception))

    def test_command_raises_error_when_no_lookup_is_provided(self):
        with self.assertRaises(CommandError) as exc:
            call_command("hik_check_device", "--tenant", "tenant-cmd")

        self.assertIn("--serial ou --dev-index", str(exc.exception))


class HikRegisterWebhooksCommandTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant Hook", code="tenant-hook")
        self.gateway = Gateway.objects.create(
            tenant=self.tenant,
            base_url="https://gw-hook.local",
            username="admin",
            password="pass",
        )
        self.device = Device.objects.create(
            gateway=self.gateway,
            tenant=self.tenant,
            serial_number="SN-HOOK",
            dev_index="IDX-HOOK",
            status="online",
        )

    @patch("hik_gateway.management.commands.hik_register_webhooks.HikGatewayClient.set_http_host")
    def test_register_webhooks_uses_http_host_notification_list_payload(self, mock_set_http_host):
        call_command(
            "hik_register_webhooks",
            "--ip-address",
            "213.156.133.202",
            "--port",
            "80",
            "--url",
            "/api/hik/events",
        )

        mock_set_http_host.assert_called_once()
        call_args = mock_set_http_host.call_args.args
        self.assertEqual(call_args[0], "IDX-HOOK")
        self.assertEqual(call_args[1]["HttpHostNotificationList"][0]["HttpHostNotification"]["url"], "/api/hik/events")
        self.assertEqual(call_args[1]["HttpHostNotificationList"][0]["HttpHostNotification"]["ipAddress"], "213.156.133.202")
        self.assertEqual(call_args[1]["HttpHostNotificationList"][0]["HttpHostNotification"]["portNo"], 80)



class HikDevicesPageTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant UI", code="tenant-ui")
        self.gateway = Gateway.objects.create(
            tenant=self.tenant,
            base_url="https://gw-ui.local",
            username="admin",
            password="pass",
        )

    @patch("hik_gateway.views.HikGatewayClient.device_list")
    def test_page_displays_devices_from_search_result_payload(self, mock_device_list):
        mock_device_list.return_value = {
            "SearchResult": {
                "MatchList": [
                    {
                        "Device": {
                            "EhomeParams": {"EhomeID": "FN2090414"},
                            "devIndex": "IDX-UI-1",
                            "devName": "Access Controller",
                            "devStatus": "online",
                            "protocolType": "ehomeV5",
                            "devType": "AccessControl",
                        }
                    }
                ]
            }
        }

        response = self.client.get("/api/hik/devices?tenant=tenant-ui")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Access Controller")
        self.assertContains(response, "FN2090414")
        self.assertContains(response, "IDX-UI-1")

    def test_page_requires_tenant_for_non_admin(self):
        response = self.client.get("/api/hik/devices")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertContains(response, "Ajoute ?tenant=&lt;code_tenant&gt;", status_code=status.HTTP_403_FORBIDDEN)

    @patch("hik_gateway.views.HikGatewayClient.device_list")
    def test_admin_can_list_devices_for_all_tenants_without_filter(self, mock_device_list):
        tenant_2 = Tenant.objects.create(name="Tenant UI 2", code="tenant-ui-2")
        Gateway.objects.create(
            tenant=tenant_2,
            base_url="https://gw-ui-2.local",
            username="admin",
            password="pass",
        )

        mock_device_list.side_effect = [
            {"SearchResult": {"MatchList": [{"Device": {"EhomeParams": {"EhomeID": "FN-1"}, "devIndex": "IDX-1", "devName": "Reader A", "devStatus": "online"}}]}},
            {"SearchResult": {"MatchList": [{"Device": {"EhomeParams": {"EhomeID": "FN-2"}, "devIndex": "IDX-2", "devName": "Reader B", "devStatus": "offline"}}]}},
        ]

        user_model = get_user_model()
        admin_user = user_model.objects.create_user(username="admin-ui", password="pass", is_staff=True)
        self.client.force_login(admin_user)

        response = self.client.get("/api/hik/devices")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Reader A")
        self.assertContains(response, "Reader B")
        self.assertContains(response, "tenant-ui")
        self.assertContains(response, "tenant-ui-2")
        self.assertEqual(mock_device_list.call_count, 2)
