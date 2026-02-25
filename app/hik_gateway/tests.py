from io import StringIO
from unittest.mock import patch

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
