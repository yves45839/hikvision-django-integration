from datetime import datetime
from datetime import timezone as dt_timezone
from io import BytesIO, StringIO
from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework import status
from rest_framework.test import APITestCase
from openpyxl import load_workbook

from employees.models import Department, Employee, EmployeeCard, Organization, WorkShift
from hik_gateway.models import AttendanceCorrection, AttendanceCorrectionLog, AttendanceLog, Device, Gateway, RawEvent
from hik_gateway.services.webhook_ingest import ingest_event
from tenants.models import Tenant


class HikAttendancePersonLinkingTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant Person", code="tenant-person")
        self.gateway = Gateway.objects.create(
            tenant=self.tenant,
            base_url="https://gw-person.local",
            username="admin",
            password="pass",
        )
        self.device = Device.objects.create(
            gateway=self.gateway,
            tenant=self.tenant,
            serial_number="SN-PERSON",
            dev_index="IDX-PERSON",
            status="online",
        )

    def _event_payload(self, **access_event):
        return {
            "EventNotificationAlert": {
                "eventType": "AccessControllerEvent",
                "devIndex": self.device.dev_index,
                "dateTime": "2026-03-01T08:00:00Z",
                "AccessControllerEvent": {
                    "attendanceStatus": "checkin",
                    "serialNo": "7001",
                    "subEventType": 1,
                    **access_event,
                },
            }
        }

    def test_ingest_links_employee_from_employee_no_string(self):
        employee = Employee.objects.create(
            tenant=self.tenant,
            employee_no="E-LINK-001",
            name="Linked User",
        )

        _, attendance = ingest_event(
            self._event_payload(employeeNoString="E-LINK-001"),
            source=AttendanceLog.SOURCE_REALTIME,
            tenant=self.tenant,
        )

        self.assertIsNotNone(attendance)
        self.assertEqual(attendance.employee_id, employee.id)
        self.assertEqual(attendance.person_id, "E-LINK-001")

    def test_ingest_links_employee_from_card_when_employee_number_missing(self):
        employee = Employee.objects.create(
            tenant=self.tenant,
            employee_no="E-LINK-002",
            name="Card Linked User",
        )
        EmployeeCard.objects.create(employee=employee, card_no="CARD-900")

        _, attendance = ingest_event(
            self._event_payload(cardNo="CARD-900"),
            source=AttendanceLog.SOURCE_REALTIME,
            tenant=self.tenant,
        )

        self.assertIsNotNone(attendance)
        self.assertEqual(attendance.employee_id, employee.id)
        self.assertEqual(attendance.person_id, "E-LINK-002")

    def test_ingest_keeps_unmatched_person_as_unresolved(self):
        _, attendance = ingest_event(
            self._event_payload(employeeNoString="UNKNOWN-EMP"),
            source=AttendanceLog.SOURCE_REALTIME,
            tenant=self.tenant,
        )

        self.assertIsNotNone(attendance)
        self.assertIsNone(attendance.employee_id)
        self.assertEqual(attendance.person_id, "UNKNOWN-EMP")

    def test_ingest_normalizes_checkin_action(self):
        _, attendance = ingest_event(
            self._event_payload(employeeNoString="E-LINK-003", attendanceStatus="checkin", serialNo="7003"),
            source=AttendanceLog.SOURCE_REALTIME,
            tenant=self.tenant,
        )

        self.assertIsNotNone(attendance)
        self.assertEqual(attendance.normalized_action, AttendanceLog.ACTION_CHECK_IN)

    def test_ingest_normalizes_denied_action_from_status(self):
        payload = self._event_payload(
            employeeNoString="E-LINK-004",
            attendanceStatus="denied",
            subEventType=3,
            serialNo="7004",
        )

        _, attendance = ingest_event(
            payload,
            source=AttendanceLog.SOURCE_REALTIME,
            tenant=self.tenant,
        )

        self.assertIsNotNone(attendance)
        self.assertEqual(attendance.normalized_action, AttendanceLog.ACTION_ACCESS_DENIED)


class HikAttendanceUnknownDeviceIngestTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant Missing Device", code="tenant-missing-device")
        self.sync_patcher = patch("hik_gateway.services.webhook_ingest.sync_gateway_devices")
        self.mock_sync_gateway_devices = self.sync_patcher.start()
        self.addCleanup(self.sync_patcher.stop)

    def _event_payload(self):
        return {
            "EventNotificationAlert": {
                "eventType": "AccessControllerEvent",
                "devIndex": "IDX-UNKNOWN",
                "dateTime": "2026-03-01T08:00:00Z",
                "AccessControllerEvent": {
                    "attendanceStatus": "checkin",
                    "employeeNoString": "E-UNRESOLVED-1",
                    "serialNo": "81001",
                    "subEventType": 1,
                    "majorEventType": 2,
                    "doorNo": 1,
                    "cardReaderNo": 2,
                },
            }
        }

    def test_ingest_stores_raw_event_even_when_device_is_not_found(self):
        raw_event, attendance = ingest_event(
            self._event_payload(),
            source=AttendanceLog.SOURCE_REALTIME,
            tenant=self.tenant,
        )

        self.assertIsNotNone(raw_event)
        self.assertIsNone(attendance)
        self.assertEqual(raw_event.tenant_id, self.tenant.id)
        self.assertIsNone(raw_event.device_id)
        self.assertEqual(raw_event.dev_index, "IDX-UNKNOWN")
        self.assertEqual(raw_event.employee_no_string, "E-UNRESOLVED-1")
        self.assertEqual(raw_event.serial_no, 81001)
        self.assertEqual(RawEvent.objects.count(), 1)
        self.assertEqual(AttendanceLog.objects.count(), 0)

    def test_ingest_is_idempotent_for_unresolved_device_events(self):
        first_raw, first_attendance = ingest_event(
            self._event_payload(),
            source=AttendanceLog.SOURCE_REALTIME,
            tenant=self.tenant,
        )
        second_raw, second_attendance = ingest_event(
            self._event_payload(),
            source=AttendanceLog.SOURCE_REALTIME,
            tenant=self.tenant,
        )

        self.assertIsNotNone(first_raw)
        self.assertIsNone(first_attendance)
        self.assertEqual(second_raw.id, first_raw.id)
        self.assertIsNone(second_attendance)
        self.assertEqual(RawEvent.objects.count(), 1)
        self.assertEqual(AttendanceLog.objects.count(), 0)


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

    def test_webhook_keeps_denied_or_non_directional_events_in_attendance_log(self):
        payload = {
            "EventNotificationAlert": {
                "eventType": "AccessControllerEvent",
                "devIndex": "shared-dev-index",
                "dateTime": "2026-02-01T08:05:00Z",
                "AccessControllerEvent": {
                    "employeeNoString": "E2001",
                    "serialNo": "102",
                    "subEventType": 3,
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

        attendance = AttendanceLog.objects.get()
        self.assertEqual(attendance.person_id, "E2001")
        self.assertEqual(attendance.direction, "UNKNOWN")
        self.assertEqual(attendance.attendance_type, "fallback")

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

    def test_webhook_dedupe_is_scoped_per_tenant(self):
        payload = {
            "EventNotificationAlert": {
                "eventType": "AccessControllerEvent",
                "devIndex": "shared-dev-index",
                "dateTime": "2026-02-01T08:00:00Z",
                "AccessControllerEvent": {
                    "attendanceStatus": "checkin",
                    "employeeNoString": "E1003",
                    "serialNo": "103",
                    "subEventType": 1,
                },
            }
        }

        response_a = self.client.post(
            "/api/hikvision/events",
            payload,
            format="json",
            HTTP_X_TENANT_CODE="tenant-a",
        )
        response_b = self.client.post(
            "/api/hikvision/events",
            payload,
            format="json",
            HTTP_X_TENANT_CODE="tenant-b",
        )

        self.assertEqual(response_a.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response_b.status_code, status.HTTP_201_CREATED)
        self.assertEqual(RawEvent.objects.count(), 2)
        self.assertEqual(AttendanceLog.objects.count(), 2)
        self.assertSetEqual(
            set(RawEvent.objects.values_list("tenant__code", flat=True)),
            {"tenant-a", "tenant-b"},
        )


class HikCheckDeviceCommandTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant Cmd", code="tenant-cmd")
        self.gateway = Gateway.objects.create(
            tenant=self.tenant,
            base_url="https://gw.local",
            username="admin",
            password="pass",
        )

    @patch("hik_gateway.services.gateway_connection.HikGatewayClient.device_list")
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

    @patch("hik_gateway.services.gateway_connection.HikGatewayClient.device_list")
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

    @patch("hik_gateway.services.gateway_connection.HikGatewayClient.set_http_host")
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

    @patch("hik_gateway.services.gateway_connection.HikGatewayClient.device_list")
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

    @patch("hik_gateway.services.gateway_connection.HikGatewayClient.device_list")
    def test_page_can_return_json_when_requested(self, mock_device_list):
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

        response = self.client.get("/api/hik/devices?tenant=tenant-ui&format=json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["dev_index"], "IDX-UI-1")

    def test_page_returns_json_error_when_tenant_missing(self):
        response = self.client.get("/api/hik/devices?format=json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        payload = response.json()
        self.assertIn("Ajoute ?tenant=<code_tenant>", payload["detail"])

    @patch("hik_gateway.services.gateway_connection.HikGatewayClient.device_list")
    def test_admin_can_list_devices_for_all_tenants_without_filter(self, mock_device_list):
        tenant_2 = Tenant.objects.create(name="Tenant UI 2", code="tenant-ui-2")
        gateway_2 = Gateway.objects.create(
            tenant=tenant_2,
            base_url="https://gw-ui-2.local",
            username="admin",
            password="pass",
        )

        Device.objects.create(
            gateway=self.gateway,
            tenant=self.tenant,
            serial_number="FN-1",
            dev_index="IDX-1",
            status="online",
        )
        Device.objects.create(
            gateway=gateway_2,
            tenant=tenant_2,
            serial_number="FN-2",
            dev_index="IDX-2",
            status="offline",
        )

        mock_device_list.return_value = {
            "SearchResult": {
                "MatchList": [
                    {"Device": {"EhomeParams": {"EhomeID": "FN-1"}, "devIndex": "IDX-1", "devName": "Reader A", "devStatus": "online"}},
                    {"Device": {"EhomeParams": {"EhomeID": "FN-2"}, "devIndex": "IDX-2", "devName": "Reader B", "devStatus": "offline"}},
                ]
            }
        }

        user_model = get_user_model()
        admin_user = user_model.objects.create_user(username="admin-ui", password="pass", is_staff=True)
        self.client.force_login(admin_user)

        response = self.client.get("/api/hik/devices")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Reader A")
        self.assertContains(response, "Reader B")
        self.assertContains(response, "tenant-ui")
        self.assertContains(response, "tenant-ui-2")
        self.assertEqual(mock_device_list.call_count, 1)

    @patch("hik_gateway.services.gateway_connection.HikGatewayClient.device_list")
    def test_page_finds_tenant_case_insensitively(self, mock_device_list):
        mock_device_list.return_value = {
            "SearchResult": {
                "MatchList": [
                    {
                        "Device": {
                            "EhomeParams": {"EhomeID": "FN2090414"},
                            "devIndex": "IDX-UI-1",
                            "devName": "Access Controller",
                            "devStatus": "online",
                        }
                    }
                ]
            }
        }

        response = self.client.get("/api/hik/devices?tenant=TENANT-UI")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Access Controller")
        self.assertContains(response, "FN2090414")

    @patch("hik_gateway.services.gateway_connection.HikGatewayClient.device_list")
    def test_page_allows_unassigned_only_for_authenticated_non_admin(self, mock_device_list):
        mock_device_list.return_value = {
            "SearchResult": {
                "MatchList": [
                    {
                        "Device": {
                            "EhomeParams": {"EhomeID": "SN-UNASSIGNED"},
                            "devIndex": "IDX-UNASSIGNED",
                            "devName": "Reader Unassigned",
                            "devStatus": "online",
                        }
                    }
                ]
            }
        }

        user_model = get_user_model()
        user = user_model.objects.create_user(username="viewer-unassigned", password="pass")
        self.client.force_login(user)

        response = self.client.get("/api/hik/devices?unassigned_only=1&format=json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["dev_index"], "IDX-UNASSIGNED")
        self.assertEqual(payload["results"][0]["tenant_code"], "")


class HikDevicesApiTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant API", code="tenant-api")
        self.gateway = Gateway.objects.create(
            tenant=self.tenant,
            base_url="https://gw-api.local",
            username="admin",
            password="pass",
        )
        user_model = get_user_model()
        user = user_model.objects.create_user(username="api-user", password="pass", is_staff=True)
        self.client.force_authenticate(user=user)

    @patch("hik_gateway.services.gateway_connection.HikGatewayClient.device_list_all")
    def test_devices_api_returns_normalized_mapping(self, mock_device_list_all):
        mock_device_list_all.return_value = {
            "SearchResult": {
                "numOfMatches": 1,
                "totalMatches": 1,
                "MatchList": [
                    {
                        "Device": {
                            "EhomeParams": {"EhomeID": "SN-ISUP5"},
                            "devIndex": "IDX-100",
                            "devName": "Main Controller",
                            "devStatus": "online",
                            "protocolType": "ehomeV5",
                            "devType": "AccessControl",
                            "devVersion": "V1.2",
                            "devSerial": "ABC123",
                        }
                    }
                ],
            }
        }

        response = self.client.get(
            "/api/hikgateway/devices/?tenant=tenant-api&protocol=ehomeV5&status=online"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["sn"], "SN-ISUP5")
        self.assertEqual(payload["results"][0]["devIndex"], "IDX-100")
        self.assertEqual(payload["results"][0]["status"], "online")
        mock_device_list_all.assert_called_once_with(
            max_result=100,
            protocol_types=["ehomeV5"],
            statuses=["online"],
            dev_type="",
            key="",
        )

    @patch("hik_gateway.services.gateway_connection.HikGatewayClient.device_list_all")
    def test_devices_api_can_return_raw_search_result_per_gateway(self, mock_device_list_all):
        mock_device_list_all.return_value = {
            "SearchResult": {
                "numOfMatches": 0,
                "totalMatches": 0,
                "MatchList": [],
            }
        }

        response = self.client.get("/api/hikgateway/devices/?tenant=tenant-api&normalized=0")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertIn("search_result", payload["results"][0])
        self.assertEqual(payload["results"][0]["tenant_code"], "tenant-api")

    @patch("hik_gateway.services.gateway_connection.HikGatewayClient.device_list_all")
    def test_devices_api_allows_unassigned_only_for_authenticated_non_admin(self, mock_device_list_all):
        mock_device_list_all.return_value = {
            "SearchResult": {
                "numOfMatches": 1,
                "totalMatches": 1,
                "MatchList": [
                    {
                        "Device": {
                            "EhomeParams": {"EhomeID": "SN-UNASSIGNED"},
                            "devIndex": "IDX-UNASSIGNED",
                            "devName": "Reader Unassigned",
                            "devStatus": "online",
                        }
                    }
                ],
            }
        }
        user_model = get_user_model()
        user = user_model.objects.create_user(username="api-user-unassigned", password="pass")
        self.client.force_authenticate(user=user)

        response = self.client.get("/api/hikgateway/devices/?unassigned_only=1")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["devIndex"], "IDX-UNASSIGNED")
        self.assertEqual(payload["results"][0]["tenant_code"], "")


class _DummyResponse:
    def __init__(self, payload):
        self._payload = payload
        self.content = b"{}"

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class HikGatewayClientPaginationTests(APITestCase):
    @patch("hik_gateway.client.requests.post")
    def test_device_list_all_fetches_all_pages(self, mock_post):
        from hik_gateway.client import HikGatewayClient

        mock_post.side_effect = [
            _DummyResponse(
                {
                    "SearchResult": {
                        "numOfMatches": 1,
                        "totalMatches": 2,
                        "MatchList": [{"Device": {"devIndex": "IDX-1"}}],
                    }
                }
            ),
            _DummyResponse(
                {
                    "SearchResult": {
                        "numOfMatches": 1,
                        "totalMatches": 2,
                        "MatchList": [{"Device": {"devIndex": "IDX-2"}}],
                    }
                }
            ),
        ]

        client = HikGatewayClient("https://gw.local", "admin", "pass")
        payload = client.device_list_all(max_result=1)

        self.assertEqual(payload["SearchResult"]["numOfMatches"], 2)
        self.assertEqual(len(payload["SearchResult"]["MatchList"]), 2)
        self.assertEqual(mock_post.call_count, 2)


class HikDeviceDispatchTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant Dispatch", code="tenant-dispatch")
        gateway = Gateway.objects.create(
            tenant=self.tenant,
            base_url="https://gw-dispatch.local",
            username="admin",
            password="pass",
        )
        Device.objects.create(
            gateway=gateway,
            tenant=self.tenant,
            serial_number="SN-DISPATCH",
            dev_index="IDX-DISPATCH",
            device_id="DEVICE-1",
            device_name="Dispatch Reader",
            protocol_type="ehomeV5",
            status="online",
        )

    def test_dispatch_service_syncs_into_core_devices_table(self):
        from devices.models import Device as CoreDevice
        from hik_gateway.services.device_dispatch import dispatch_hik_devices_to_core_devices

        count = dispatch_hik_devices_to_core_devices()

        self.assertEqual(count, 1)
        core_device = CoreDevice.objects.get(dev_index="IDX-DISPATCH")
        self.assertEqual(core_device.tenant, self.tenant)
        self.assertEqual(core_device.serial_number, "SN-DISPATCH")
        self.assertEqual(core_device.device_id, "DEVICE-1")
        self.assertEqual(core_device.name, "Dispatch Reader")
        self.assertEqual(core_device.protocol, "ehomeV5")

    def test_dispatch_preserves_existing_core_device_name(self):
        from devices.models import Device as CoreDevice
        from hik_gateway.services.device_dispatch import dispatch_hik_devices_to_core_devices

        CoreDevice.objects.create(
            tenant=self.tenant,
            serial_number="SN-DISPATCH",
            dev_index="IDX-DISPATCH",
            name="Nom Personnalise",
            protocol="ISUP",
            status="offline",
        )

        count = dispatch_hik_devices_to_core_devices()

        self.assertEqual(count, 1)
        core_device = CoreDevice.objects.get(dev_index="IDX-DISPATCH")
        self.assertEqual(core_device.name, "Nom Personnalise")
        self.assertEqual(core_device.device_id, "DEVICE-1")
        self.assertEqual(core_device.protocol, "ehomeV5")

    def test_dispatch_fills_name_when_existing_core_name_is_blank(self):
        from devices.models import Device as CoreDevice
        from hik_gateway.services.device_dispatch import dispatch_hik_devices_to_core_devices

        CoreDevice.objects.create(
            tenant=self.tenant,
            serial_number="SN-DISPATCH",
            dev_index="IDX-DISPATCH",
            name="",
            protocol="ISUP",
            status="offline",
        )

        count = dispatch_hik_devices_to_core_devices()

        self.assertEqual(count, 1)
        core_device = CoreDevice.objects.get(dev_index="IDX-DISPATCH")
        self.assertEqual(core_device.name, "Dispatch Reader")


class HikSyncDevicesCommandTests(APITestCase):
    @patch("hik_gateway.management.commands.hik_sync_devices.sync_all_gateways")
    def test_command_runs_sync_once_by_default(self, mock_sync_all_gateways):
        mock_sync_all_gateways.return_value = 3

        stdout = StringIO()
        call_command("hik_sync_devices", stdout=stdout)

        self.assertIn("Synced 3 devices", stdout.getvalue())

    def test_command_rejects_loop_without_interval(self):
        with self.assertRaises(CommandError) as exc:
            call_command("hik_sync_devices", "--loop")

        self.assertIn("--loop nécessite --interval > 0", str(exc.exception))


class HikDeviceDevicesSpaceTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant Space", code="tenant-space")
        self.gateway = Gateway.objects.create(
            tenant=self.tenant,
            base_url="https://gw-space.local",
            username="admin",
            password="pass",
        )

    @patch("hik_gateway.services.gateway_connection.HikGatewayClient.device_list_all")
    def test_space_displays_gateway_devices(self, mock_device_list_all):
        Device.objects.create(
            gateway=self.gateway,
            tenant=self.tenant,
            serial_number="SN-SPACE",
            dev_index="IDX-SPACE",
            status="online",
        )
        mock_device_list_all.return_value = {
            "SearchResult": {
                "MatchList": [
                    {
                        "Device": {
                            "EhomeParams": {"EhomeID": "SN-SPACE"},
                            "devIndex": "IDX-SPACE",
                            "devName": "Porte principale",
                            "devStatus": "online",
                            "protocolType": "ehomeV5",
                            "devType": "AccessControl",
                        }
                    }
                ]
            }
        }

        response = self.client.get("/api/hikdevice/devices?tenant=tenant-space")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Espace HikDevice")
        self.assertContains(response, "Porte principale")
        self.assertContains(response, "SN-SPACE")

    def test_space_requires_tenant_for_non_admin(self):
        response = self.client.get("/api/hikdevice/devices")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertContains(response, "Ajoute ?tenant=&lt;code_tenant&gt;", status_code=status.HTTP_403_FORBIDDEN)

    @patch("hik_gateway.services.gateway_connection.HikGatewayClient.device_list_all")
    def test_space_allows_unassigned_only_for_authenticated_non_admin(self, mock_device_list_all):
        mock_device_list_all.return_value = {
            "SearchResult": {
                "MatchList": [
                    {
                        "Device": {
                            "EhomeParams": {"EhomeID": "SN-UNASSIGNED"},
                            "devIndex": "IDX-UNASSIGNED",
                            "devName": "Reader Unassigned",
                            "devStatus": "online",
                        }
                    }
                ]
            }
        }
        user_model = get_user_model()
        user = user_model.objects.create_user(username="space-user", password="pass")
        self.client.force_login(user)

        response = self.client.get("/api/hikdevice/devices?unassigned_only=1")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Reader Unassigned")


class HikGatewayAdminApiTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant Admin API", code="tenant-admin-api")
        self.gateway = Gateway.objects.create(
            tenant=self.tenant,
            base_url="https://gw-admin.local",
            username="admin",
            password="pass",
        )
        self.device = Device.objects.create(
            gateway=self.gateway,
            tenant=self.tenant,
            serial_number="SN-ADMIN",
            dev_index="IDX-ADMIN",
            status="online",
        )
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(username="admin-api", password="pass", is_staff=True)
        self.user = user_model.objects.create_user(username="simple-user", password="pass")

    def _create_attendance_log(
        self,
        *,
        person_id: str,
        timestamp: str,
        serial_no: int,
        attendance_type: str = "checkin",
        attendance_status: str = "checkin",
        direction: str = "IN",
    ) -> AttendanceLog:
        raw_event = RawEvent.objects.create(
            tenant=self.tenant,
            device=self.device,
            dev_index=self.device.dev_index,
            event_type="AccessControllerEvent",
            event_datetime=timestamp,
            major_event_type=5,
            sub_event_type=1,
            serial_no=serial_no,
            dedupe_key=f"event-{serial_no}",
            payload={"sample": True},
        )
        return AttendanceLog.objects.create(
            tenant=self.tenant,
            person_id=person_id,
            device=self.device,
            timestamp=timestamp,
            attendance_type=attendance_type,
            attendance_status=attendance_status,
            direction=direction,
            source=AttendanceLog.SOURCE_REALTIME,
            raw_event=raw_event,
        )

    def test_sync_devices_endpoint_requires_admin(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post("/api/hikgateway/sync-devices/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("hik_gateway.views.sync_all_gateways")
    @patch("hik_gateway.views.dispatch_hik_devices_to_core_devices")
    def test_sync_devices_endpoint_runs_sync(self, mock_dispatch, mock_sync):
        mock_sync.return_value = 2
        mock_dispatch.return_value = 2
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/api/hikgateway/sync-devices/",
            {"dispatch_core_devices": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["synced"], 2)
        self.assertEqual(response.json()["dispatched"], 2)

    @patch("hik_gateway.views.catchup_all_devices")
    def test_catchup_endpoint_runs(self, mock_catchup):
        mock_catchup.return_value = 5
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/api/hikgateway/catchup-acs-events/",
            {"max_results": 100},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["processed"], 5)
        mock_catchup.assert_called_once_with(max_results=100)

    @patch("hik_gateway.views.get_shared_gateway_client")
    def test_register_webhooks_endpoint_registers_all_devices(self, mock_get_client):
        mock_client = mock_get_client.return_value
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/api/hikgateway/register-webhooks/",
            {"ip_address": "213.156.133.202", "port": 443, "url": "/api/hik/events"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["registered"], 1)
        mock_client.set_http_host.assert_called_once()

    def test_register_webhooks_endpoint_requires_ip(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/api/hikgateway/register-webhooks/",
            {"ip_address": ""},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_events_endpoint_requires_tenant_for_non_admin(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/hikgateway/events/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_events_endpoint_lists_attendance_logs_for_tenant(self):
        self.client.force_authenticate(user=self.user)
        self._create_attendance_log(person_id="E1001", timestamp="2026-02-01T08:00:00Z", serial_no=100)

        response = self.client.get(
            "/api/hikgateway/events/",
            {"tenant": self.tenant.code, "source": "realtime", "dev_index": self.device.dev_index},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["person_id"], "E1001")
        self.assertEqual(payload["results"][0]["device"]["dev_index"], self.device.dev_index)

    def test_attendance_reports_endpoint_requires_tenant_for_non_admin(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get("/api/hikgateway/reports/attendance/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_attendance_reports_endpoint_supports_daily_report(self):
        self.client.force_authenticate(user=self.user)
        employee = Employee.objects.create(tenant=self.tenant, employee_no="E1001", name="Alice Doe")

        first_log = self._create_attendance_log(
            person_id=employee.employee_no,
            timestamp="2026-02-10T08:00:00Z",
            serial_no=110,
            attendance_type="checkin",
            attendance_status="checkin",
            direction="IN",
        )
        first_log.employee = employee
        first_log.save(update_fields=["employee"])

        second_log = self._create_attendance_log(
            person_id=employee.employee_no,
            timestamp="2026-02-10T17:15:00Z",
            serial_no=111,
            attendance_type="checkout",
            attendance_status="checkout",
            direction="OUT",
        )
        second_log.employee = employee
        second_log.save(update_fields=["employee"])

        self._create_attendance_log(
            person_id="E9999",
            timestamp="2026-02-11T08:00:00Z",
            serial_no=112,
            attendance_type="checkin",
            attendance_status="checkin",
            direction="IN",
        )

        response = self.client.get(
            "/api/hikgateway/reports/attendance/",
            {"tenant": self.tenant.code, "period": "daily", "date": "2026-02-10"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["period"], "daily")
        self.assertEqual(payload["range"]["start_date"], "2026-02-10")
        self.assertEqual(payload["range"]["end_date"], "2026-02-10")
        self.assertEqual(payload["summary"]["total_logs"], 2)
        self.assertEqual(payload["summary"]["checkins"], 1)
        self.assertEqual(payload["summary"]["checkouts"], 1)
        self.assertEqual(len(payload["timeline"]), 1)
        self.assertEqual(payload["timeline"][0]["date"], "2026-02-10")
        self.assertEqual(payload["employees"][0]["employee_name"], "Alice Doe")
        self.assertEqual(payload["employees"][0]["days_present"], 1)

    def test_attendance_reports_endpoint_supports_weekly_report(self):
        self.client.force_authenticate(user=self.user)

        self._create_attendance_log(
            person_id="E2001",
            timestamp="2026-02-09T08:00:00Z",
            serial_no=120,
            attendance_type="checkin",
            attendance_status="checkin",
            direction="IN",
        )
        self._create_attendance_log(
            person_id="E2001",
            timestamp="2026-02-10T17:00:00Z",
            serial_no=121,
            attendance_type="checkout",
            attendance_status="checkout",
            direction="OUT",
        )
        self._create_attendance_log(
            person_id="E2002",
            timestamp="2026-02-15T09:30:00Z",
            serial_no=122,
            attendance_type="fallback",
            attendance_status="",
            direction="UNKNOWN",
        )
        self._create_attendance_log(
            person_id="E2003",
            timestamp="2026-02-16T08:00:00Z",
            serial_no=123,
            attendance_type="checkin",
            attendance_status="checkin",
            direction="IN",
        )

        response = self.client.get(
            "/api/hikgateway/reports/attendance/",
            {"tenant": self.tenant.code, "period": "weekly", "date": "2026-02-10"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["range"]["start_date"], "2026-02-09")
        self.assertEqual(payload["range"]["end_date"], "2026-02-15")
        self.assertEqual(payload["summary"]["total_logs"], 3)
        self.assertEqual(payload["summary"]["unknown_events"], 1)
        self.assertEqual(len(payload["timeline"]), 3)
        self.assertEqual(payload["timeline"][0]["date"], "2026-02-09")

    def test_attendance_reports_endpoint_supports_monthly_custom_range(self):
        self.client.force_authenticate(user=self.admin)

        self._create_attendance_log(
            person_id="E3001",
            timestamp="2026-03-01T08:00:00Z",
            serial_no=130,
            attendance_type="checkin",
            attendance_status="checkin",
            direction="IN",
        )
        self._create_attendance_log(
            person_id="E3001",
            timestamp="2026-03-20T18:00:00Z",
            serial_no=131,
            attendance_type="checkout",
            attendance_status="checkout",
            direction="OUT",
        )
        self._create_attendance_log(
            person_id="E3002",
            timestamp="2026-04-01T08:00:00Z",
            serial_no=132,
            attendance_type="checkin",
            attendance_status="checkin",
            direction="IN",
        )

        response = self.client.get(
            "/api/hikgateway/reports/attendance/",
            {"period": "monthly", "start_date": "2026-03-01", "end_date": "2026-03-31"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["summary"]["total_logs"], 2)
        self.assertEqual(payload["summary"]["total_employees"], 1)
        self.assertEqual(payload["filters"]["tenant"], None)
        self.assertEqual(payload["employees"][0]["person_id"], "E3001")

    def test_attendance_reports_endpoint_supports_excel_export(self):
        self.client.force_authenticate(user=self.user)
        employee = Employee.objects.create(tenant=self.tenant, employee_no="E3501", name="Export Excel User")
        log = self._create_attendance_log(
            person_id=employee.employee_no,
            timestamp="2026-03-05T08:05:00Z",
            serial_no=135,
            attendance_type="checkin",
            attendance_status="checkin",
            direction="IN",
        )
        log.employee = employee
        log.save(update_fields=["employee"])

        response = self.client.get(
            "/api/hikgateway/reports/attendance/",
            {
                "tenant": self.tenant.code,
                "period": "daily",
                "date": "2026-03-05",
                "person_id": employee.employee_no,
                "export": "excel",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            response["Content-Type"],
        )
        self.assertIn(".xlsx", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"PK"))
        workbook = load_workbook(BytesIO(response.content))
        sheet = workbook.active
        header_row = [cell.value for cell in sheet[5]]
        self.assertIn("Heure arrivee", header_row)
        self.assertIn("Heure depart", header_row)

    def test_attendance_reports_endpoint_supports_pdf_export(self):
        self.client.force_authenticate(user=self.user)
        employee = Employee.objects.create(tenant=self.tenant, employee_no="E3502", name="Export PDF User")
        log = self._create_attendance_log(
            person_id=employee.employee_no,
            timestamp="2026-03-06T08:10:00Z",
            serial_no=136,
            attendance_type="checkin",
            attendance_status="checkin",
            direction="IN",
        )
        log.employee = employee
        log.save(update_fields=["employee"])

        response = self.client.get(
            "/api/hikgateway/reports/attendance/",
            {
                "tenant": self.tenant.code,
                "period": "daily",
                "date": "2026-03-06",
                "person_id": employee.employee_no,
                "export": "pdf",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("application/pdf", response["Content-Type"])
        self.assertIn(".pdf", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_attendance_reports_endpoint_supports_person_ids_and_compliance(self):
        self.client.force_authenticate(user=self.user)
        organization = Organization.objects.create(tenant=self.tenant, name="Ops", code="ops")
        department = Department.objects.create(
            tenant=self.tenant,
            organization=organization,
            name="Security",
            code="security",
        )
        shift = WorkShift.objects.create(
            tenant=self.tenant,
            name="Day Shift",
            code="day-shift",
            start_time="08:00",
            end_time="17:00",
        )
        employee_ok = Employee.objects.create(
            tenant=self.tenant,
            department=department,
            employee_no="E4001",
            name="Compliant User",
            work_shift=shift,
        )
        employee_missing = Employee.objects.create(
            tenant=self.tenant,
            department=department,
            employee_no="E4002",
            name="Missing User",
            work_shift=shift,
        )

        checkin = self._create_attendance_log(
            person_id=employee_ok.employee_no,
            timestamp="2026-02-12T08:00:00Z",
            serial_no=140,
            attendance_type="checkin",
            attendance_status="checkin",
            direction="IN",
        )
        checkin.employee = employee_ok
        checkin.save(update_fields=["employee"])

        checkout = self._create_attendance_log(
            person_id=employee_ok.employee_no,
            timestamp="2026-02-12T17:00:00Z",
            serial_no=141,
            attendance_type="checkout",
            attendance_status="checkout",
            direction="OUT",
        )
        checkout.employee = employee_ok
        checkout.save(update_fields=["employee"])

        response = self.client.get(
            "/api/hikgateway/reports/attendance/",
            {
                "tenant": self.tenant.code,
                "period": "daily",
                "date": "2026-02-12",
                "person_ids": f"{employee_ok.employee_no},{employee_missing.employee_no}",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["filters"]["person_ids"], [employee_ok.employee_no, employee_missing.employee_no])
        self.assertIn("compliance", payload)
        self.assertEqual(payload["compliance"]["summary"]["evaluated_employees"], 2)
        self.assertEqual(payload["compliance"]["summary"]["expected_work_days"], 2)
        self.assertEqual(payload["compliance"]["summary"]["compliant_days"], 1)
        self.assertEqual(payload["compliance"]["summary"]["missing_days"], 1)

    def test_attendance_reports_endpoint_filters_by_department_id(self):
        self.client.force_authenticate(user=self.user)
        organization = Organization.objects.create(tenant=self.tenant, name="HQ", code="hq")
        department_a = Department.objects.create(
            tenant=self.tenant,
            organization=organization,
            name="A Team",
            code="a-team",
        )
        department_b = Department.objects.create(
            tenant=self.tenant,
            organization=organization,
            name="B Team",
            code="b-team",
        )
        employee_a = Employee.objects.create(
            tenant=self.tenant,
            department=department_a,
            employee_no="E5001",
            name="Dept A User",
        )
        employee_b = Employee.objects.create(
            tenant=self.tenant,
            department=department_b,
            employee_no="E5002",
            name="Dept B User",
        )
        log_a = self._create_attendance_log(
            person_id=employee_a.employee_no,
            timestamp="2026-02-13T08:00:00Z",
            serial_no=150,
            attendance_type="checkin",
            attendance_status="checkin",
            direction="IN",
        )
        log_a.employee = employee_a
        log_a.save(update_fields=["employee"])
        log_b = self._create_attendance_log(
            person_id=employee_b.employee_no,
            timestamp="2026-02-13T08:10:00Z",
            serial_no=151,
            attendance_type="checkin",
            attendance_status="checkin",
            direction="IN",
        )
        log_b.employee = employee_b
        log_b.save(update_fields=["employee"])

        response = self.client.get(
            "/api/hikgateway/reports/attendance/",
            {
                "tenant": self.tenant.code,
                "period": "daily",
                "date": "2026-02-13",
                "department_id": department_a.id,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["filters"]["department_id"], department_a.id)
        self.assertEqual(payload["summary"]["total_logs"], 1)
        self.assertEqual(len(payload["employees"]), 1)
        self.assertEqual(payload["employees"][0]["person_id"], employee_a.employee_no)
        self.assertEqual(len(payload["compliance"]["employees"]), 1)
        self.assertEqual(payload["compliance"]["employees"][0]["person_id"], employee_a.employee_no)

    def test_attendance_reports_compliance_details_include_planned_vs_actual_times(self):
        self.client.force_authenticate(user=self.user)
        organization = Organization.objects.create(tenant=self.tenant, name="Ops 2", code="ops-2")
        department = Department.objects.create(
            tenant=self.tenant,
            organization=organization,
            name="Control Room",
            code="control-room",
        )
        shift = WorkShift.objects.create(
            tenant=self.tenant,
            name="Morning Shift",
            code="morning-shift",
            start_time="08:00",
            end_time="17:00",
        )
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=department,
            employee_no="E6001",
            name="Timing User",
            work_shift=shift,
        )

        checkin = self._create_attendance_log(
            person_id=employee.employee_no,
            timestamp="2026-02-14T08:07:00Z",
            serial_no=160,
            attendance_type="checkin",
            attendance_status="checkin",
            direction="IN",
        )
        checkin.employee = employee
        checkin.save(update_fields=["employee"])
        checkout = self._create_attendance_log(
            person_id=employee.employee_no,
            timestamp="2026-02-14T16:45:00Z",
            serial_no=161,
            attendance_type="checkout",
            attendance_status="checkout",
            direction="OUT",
        )
        checkout.employee = employee
        checkout.save(update_fields=["employee"])

        response = self.client.get(
            "/api/hikgateway/reports/attendance/",
            {
                "tenant": self.tenant.code,
                "period": "daily",
                "date": "2026-02-14",
                "person_id": employee.employee_no,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        details = payload["compliance"]["employees"][0]["details"]
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["expected_checkin_at"], "2026-02-14T08:00:00Z")
        self.assertEqual(details[0]["expected_checkout_at"], "2026-02-14T17:00:00Z")
        self.assertEqual(details[0]["actual_checkin_at"], "2026-02-14T08:07:00Z")
        self.assertEqual(details[0]["actual_checkout_at"], "2026-02-14T16:45:00Z")
        self.assertEqual(details[0]["arrival_delta_minutes"], 7)
        self.assertEqual(details[0]["departure_delta_minutes"], -15)

    def test_attendance_reports_assigns_overnight_checkout_to_shift_start_day(self):
        self.client.force_authenticate(user=self.user)
        organization = Organization.objects.create(tenant=self.tenant, name="Ops Night", code="ops-night")
        department = Department.objects.create(
            tenant=self.tenant,
            organization=organization,
            name="Night Room",
            code="night-room",
        )
        night_shift = WorkShift.objects.create(
            tenant=self.tenant,
            name="Night Shift",
            code="night-shift",
            start_time="22:00",
            end_time="06:00",
        )
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=department,
            employee_no="E6002",
            name="Night User",
            work_shift=night_shift,
        )
        employee.work_shifts.set([night_shift])

        checkin = self._create_attendance_log(
            person_id=employee.employee_no,
            timestamp="2026-02-14T22:05:00Z",
            serial_no=162,
            attendance_type="checkin",
            attendance_status="checkin",
            direction="IN",
        )
        checkin.employee = employee
        checkin.save(update_fields=["employee"])

        checkout = self._create_attendance_log(
            person_id=employee.employee_no,
            timestamp="2026-02-15T05:55:00Z",
            serial_no=163,
            attendance_type="checkout",
            attendance_status="checkout",
            direction="OUT",
        )
        checkout.employee = employee
        checkout.save(update_fields=["employee"])

        response = self.client.get(
            "/api/hikgateway/reports/attendance/",
            {
                "tenant": self.tenant.code,
                "period": "daily",
                "date": "2026-02-14",
                "person_id": employee.employee_no,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["summary"]["total_logs"], 2)
        self.assertEqual(payload["summary"]["checkins"], 1)
        self.assertEqual(payload["summary"]["checkouts"], 1)
        self.assertEqual(len(payload["timeline"]), 1)
        self.assertEqual(payload["timeline"][0]["date"], "2026-02-14")

        details = payload["compliance"]["employees"][0]["details"]
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["date"], "2026-02-14")
        self.assertEqual(details[0]["expected_checkin_at"], "2026-02-14T22:00:00Z")
        self.assertEqual(details[0]["expected_checkout_at"], "2026-02-15T06:00:00Z")
        self.assertEqual(details[0]["actual_checkin_at"], "2026-02-14T22:05:00Z")
        self.assertEqual(details[0]["actual_checkout_at"], "2026-02-15T05:55:00Z")
        self.assertEqual(details[0]["arrival_delta_minutes"], 5)
        self.assertEqual(details[0]["departure_delta_minutes"], -5)
        self.assertEqual(details[0]["matched_shift"]["code"], "night-shift")

    def test_attendance_reports_include_executive_summary_and_hr_fields(self):
        self.client.force_authenticate(user=self.user)
        organization = Organization.objects.create(tenant=self.tenant, name="Ops Exec", code="ops-exec")
        department = Department.objects.create(
            tenant=self.tenant,
            organization=organization,
            name="Operations",
            code="operations",
        )
        shift = WorkShift.objects.create(
            tenant=self.tenant,
            name="Executive Shift",
            code="executive-shift",
            start_time="08:00",
            end_time="17:00",
        )
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=department,
            employee_no="E7001",
            name="Executive User",
            position="Agent RH",
            work_shift=shift,
        )
        checkin = self._create_attendance_log(
            person_id=employee.employee_no,
            timestamp="2026-02-20T08:07:00Z",
            serial_no=170,
            attendance_type="checkin",
            attendance_status="checkin",
            direction="IN",
        )
        checkin.employee = employee
        checkin.save(update_fields=["employee"])
        checkout = self._create_attendance_log(
            person_id=employee.employee_no,
            timestamp="2026-02-20T16:45:00Z",
            serial_no=171,
            attendance_type="checkout",
            attendance_status="checkout",
            direction="OUT",
        )
        checkout.employee = employee
        checkout.save(update_fields=["employee"])

        response = self.client.get(
            "/api/hikgateway/reports/attendance/",
            {
                "tenant": self.tenant.code,
                "period": "daily",
                "date": "2026-02-20",
                "person_id": employee.employee_no,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertIn("executive_summary", payload)
        self.assertEqual(payload["executive_summary"]["effectif_total"], 1)
        self.assertEqual(payload["executive_summary"]["attendance_overview"]["late_employees"], 1)
        self.assertEqual(payload["executive_summary"]["heures"]["normal_minutes"], 518)
        self.assertEqual(payload["executive_summary"]["heures"]["overtime_minutes"], 0)
        self.assertEqual(payload["executive_summary"]["taux_ponctualite_global"], 0.0)

        employee_payload = payload["compliance"]["employees"][0]
        self.assertEqual(employee_payload["matricule"], employee.employee_no)
        self.assertEqual(employee_payload["service"], "Operations")
        self.assertEqual(employee_payload["position"], "Agent RH")
        self.assertEqual(employee_payload["late_days"], 1)
        self.assertEqual(employee_payload["early_leave_days"], 1)

        details = employee_payload["details"][0]
        self.assertEqual(details["late_minutes"], 7)
        self.assertEqual(details["early_leave_minutes"], 15)
        self.assertEqual(details["worked_minutes"], 518)
        self.assertEqual(details["normal_minutes"], 518)
        self.assertEqual(details["hr_status"], "a_verifier")
        self.assertIn("retard", details["anomaly_types"])
        self.assertIn("depart_anticipe", details["anomaly_types"])

    def test_attendance_reports_support_anomaly_and_validation_filters_with_correction_history(self):
        self.client.force_authenticate(user=self.user)
        organization = Organization.objects.create(tenant=self.tenant, name="Ops Filter", code="ops-filter")
        department = Department.objects.create(
            tenant=self.tenant,
            organization=organization,
            name="Security",
            code="security-filter",
        )
        shift = WorkShift.objects.create(
            tenant=self.tenant,
            name="Filter Shift",
            code="filter-shift",
            start_time="08:00",
            end_time="17:00",
        )
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=department,
            employee_no="E7002",
            name="Filter User",
            work_shift=shift,
        )
        work_date = datetime(2026, 2, 21, tzinfo=dt_timezone.utc).date()
        correction = AttendanceCorrection.objects.create(
            tenant=self.tenant,
            employee=employee,
            work_date=work_date,
            arrival_time="08:02",
            departure_time="17:00",
            notes="Regularisation retard",
            created_by=self.user,
            updated_by=self.user,
        )
        AttendanceCorrectionLog.objects.create(
            correction=correction,
            tenant=self.tenant,
            employee=employee,
            work_date=work_date,
            action=AttendanceCorrectionLog.ACTION_UPDATE,
            payload={
                "before": {},
                "after": {
                    "notes": "Regularisation retard",
                    "validation_status": "approved",
                },
            },
            changed_by=self.user,
        )

        response = self.client.get(
            "/api/hikgateway/reports/attendance/",
            {
                "tenant": self.tenant.code,
                "period": "daily",
                "date": "2026-02-21",
                "person_id": employee.employee_no,
                "anomaly_type": "retard",
                "validation_status": "approved",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["filters"]["anomaly_type"], ["retard"])
        self.assertEqual(payload["filters"]["validation_status"], ["approved"])
        self.assertEqual(len(payload["correction_history"]), 1)
        self.assertEqual(payload["correction_history"][0]["changed_by"], self.user.username)
        self.assertEqual(payload["correction_history"][0]["reason"], "Regularisation retard")
        details = payload["compliance"]["employees"][0]["details"]
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["validation_status"], "approved")
        self.assertIn("retard", details[0]["anomaly_types"])


class HikAcsEventsApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="acs-user", password="pass")
        self.client.force_authenticate(user=self.user)

    @patch("hik_gateway.views.get_shared_gateway_client")
    def test_acs_events_endpoint_queries_shared_gateway_without_tenant(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.acs_event_search.return_value = {
            "AcsEvent": {
                "InfoList": [
                    {
                        "major": 2,
                        "minor": 1024,
                        "serialNo": 1,
                    }
                ]
            }
        }

        response = self.client.post(
            "/api/hikgateway/acs-events/",
            {
                "dev_index": "49ACE3EE-BF88-CD49-810E-A5019FD7E7E8",
                "searchID": "123",
                "searchResultPosition": 0,
                "maxResults": 30,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["dev_index"], "49ACE3EE-BF88-CD49-810E-A5019FD7E7E8")
        self.assertIn("response", payload)
        mock_get_client.assert_called_once_with()
        mock_client.acs_event_search.assert_called_once_with(
            "49ACE3EE-BF88-CD49-810E-A5019FD7E7E8",
            {
                "AcsEventCond": {
                    "searchID": "123",
                    "searchResultPosition": 0,
                    "maxResults": 30,
                }
            },
        )

    @patch("hik_gateway.views.get_shared_gateway_client")
    def test_acs_events_endpoint_supports_get_query_params(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.acs_event_search.return_value = {"AcsEvent": {"InfoList": []}}

        response = self.client.get(
            "/api/hikgateway/acs-events/",
            {
                "dev_index": "IDX-GET-1",
                "searchID": "abc",
                "searchResultPosition": "0",
                "maxResults": "10",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_get_client.assert_called_once_with()
        mock_client.acs_event_search.assert_called_once_with(
            "IDX-GET-1",
            {
                "AcsEventCond": {
                    "searchID": "abc",
                    "searchResultPosition": 0,
                    "maxResults": 10,
                }
            },
        )

    @patch("hik_gateway.views.get_shared_gateway_client")
    def test_acs_events_endpoint_retries_without_time_window_on_bad_json(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.acs_event_search.side_effect = [
            Exception("400 badJsonContent Wrong JSON content"),
            {"AcsEvent": {"InfoList": []}},
        ]

        response = self.client.post(
            "/api/hikgateway/acs-events/",
            {
                "dev_index": "IDX-ACS-FALLBACK",
                "payload": {
                    "AcsEventCond": {
                        "searchID": "acs-fallback",
                        "searchResultPosition": 0,
                        "maxResults": 30,
                        "startTime": "2026-03-21T09:23:43Z",
                        "endTime": "2026-03-21T09:23:44Z",
                    }
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(mock_client.acs_event_search.call_count, 2)
        first_payload = mock_client.acs_event_search.call_args_list[0].args[1]
        second_payload = mock_client.acs_event_search.call_args_list[1].args[1]
        self.assertIn("startTime", first_payload["AcsEventCond"])
        self.assertNotIn("startTime", second_payload["AcsEventCond"])
        self.assertNotIn("startTime", response.json()["request"]["AcsEventCond"])

    @patch("hik_gateway.views.get_shared_gateway_client")
    def test_acs_events_endpoint_fetches_tail_page_after_fallback(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.acs_event_search.side_effect = [
            Exception("400 badJsonContent Wrong JSON content"),
            {
                "AcsEvent": {
                    "totalMatches": 130,
                    "InfoList": [{"serialNo": 1, "time": "2025-06-28T11:50:56-00:00"}],
                }
            },
            {
                "AcsEvent": {
                    "totalMatches": 130,
                    "InfoList": [{"serialNo": 130, "time": "2026-03-21T09:51:56-00:00", "cardNo": "CARD-130"}],
                }
            },
        ]

        response = self.client.post(
            "/api/hikgateway/acs-events/",
            {
                "dev_index": "IDX-ACS-TAIL",
                "payload": {
                    "AcsEventCond": {
                        "searchID": "acs-tail",
                        "searchResultPosition": 0,
                        "maxResults": 30,
                        "startTime": "2026-03-21T09:51:42Z",
                        "endTime": "2026-03-21T09:51:56Z",
                    }
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(mock_client.acs_event_search.call_count, 3)
        second_payload = mock_client.acs_event_search.call_args_list[1].args[1]
        third_payload = mock_client.acs_event_search.call_args_list[2].args[1]
        self.assertNotIn("startTime", second_payload["AcsEventCond"])
        self.assertEqual(third_payload["AcsEventCond"]["searchResultPosition"], 100)
        self.assertEqual(response.json()["request"]["AcsEventCond"]["searchResultPosition"], 100)


class HikReadCardApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="read-card-user", password="pass")
        self.client.force_authenticate(user=self.user)

    @patch("hik_gateway.views.pytime.sleep")
    @patch("hik_gateway.views.get_shared_gateway_client")
    def test_read_card_endpoint_returns_card_when_detected(self, mock_get_client, mock_sleep):
        mock_client = mock_get_client.return_value
        mock_client.acs_event_search.side_effect = [
            {"AcsEvent": {"InfoList": []}},
            {
                "AcsEvent": {
                    "InfoList": [
                        {
                            "cardNo": "CARD-4411",
                            "employeeNoString": "E-4411",
                            "serialNo": 4411,
                            "dateTime": "2099-03-01T08:00:00Z",
                            "cardReaderNo": 2,
                            "doorNo": 1,
                        }
                    ]
                }
            },
        ]

        response = self.client.post(
            "/api/hikgateway/read-card/",
            {
                "dev_index": "IDX-READ-1",
                "timeout_seconds": 2,
                "poll_interval_ms": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["dev_index"], "IDX-READ-1")
        self.assertEqual(payload["card_no"], "CARD-4411")
        self.assertEqual(payload["employee_no_string"], "E-4411")
        self.assertEqual(payload["card_reader_no"], 2)
        self.assertEqual(mock_client.acs_event_search.call_count, 2)
        mock_get_client.assert_called_once_with(tenant_code=None)
        mock_sleep.assert_called()

    @patch("hik_gateway.views.pytime.sleep")
    @patch("hik_gateway.views.get_shared_gateway_client")
    def test_read_card_endpoint_times_out_when_no_card(self, mock_get_client, mock_sleep):
        mock_client = mock_get_client.return_value
        mock_client.acs_event_search.return_value = {"AcsEvent": {"InfoList": []}}

        response = self.client.post(
            "/api/hikgateway/read-card/",
            {
                "dev_index": "IDX-READ-2",
                "timeout_seconds": 1,
                "poll_interval_ms": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_408_REQUEST_TIMEOUT)
        self.assertIn("Aucune carte", response.json()["detail"])
        self.assertGreaterEqual(mock_client.acs_event_search.call_count, 1)
        mock_sleep.assert_called()

    @patch("hik_gateway.views.get_shared_gateway_client")
    def test_read_card_endpoint_retries_without_time_window_on_bad_json(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.acs_event_search.side_effect = [
            Exception("400 badJsonContent Wrong JSON content"),
            {
                "AcsEvent": {
                    "InfoList": [
                        {
                            "cardNo": "CARD-FALLBACK-1",
                            "employeeNoString": "E-FALLBACK-1",
                            "serialNo": 9901,
                            "dateTime": "2099-03-01T08:00:00Z",
                        }
                    ]
                }
            },
        ]

        response = self.client.post(
            "/api/hikgateway/read-card/",
            {
                "dev_index": "IDX-READ-FALLBACK",
                "timeout_seconds": 3,
                "poll_interval_ms": 1000,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["card_no"], "CARD-FALLBACK-1")
        self.assertEqual(mock_client.acs_event_search.call_count, 2)
        first_payload = mock_client.acs_event_search.call_args_list[0].args[1]
        second_payload = mock_client.acs_event_search.call_args_list[1].args[1]
        self.assertIn("startTime", first_payload["AcsEventCond"])
        self.assertNotIn("startTime", second_payload["AcsEventCond"])

    @patch("hik_gateway.views.pytime.sleep")
    @patch("hik_gateway.views.get_shared_gateway_client")
    def test_read_card_endpoint_accepts_newer_serial_when_reader_time_is_stale(self, mock_get_client, mock_sleep):
        mock_client = mock_get_client.return_value
        mock_client.acs_event_search.side_effect = [
            Exception("400 badJsonContent Wrong JSON content"),
            {
                "AcsEvent": {
                    "InfoList": [
                        {
                            "cardNo": "CARD-OLD-38",
                            "employeeNoString": "E-OLD-38",
                            "serialNo": 38,
                            "time": "2026-03-21T19:37:54+08:00",
                        }
                    ]
                }
            },
            Exception("400 badJsonContent Wrong JSON content"),
            {
                "AcsEvent": {
                    "InfoList": [
                        {
                            "cardNo": "CARD-NEW-39",
                            "employeeNoString": "E-NEW-39",
                            "serialNo": 39,
                            "time": "2026-03-21T19:38:54+08:00",
                        }
                    ]
                }
            },
        ]

        response = self.client.post(
            "/api/hikgateway/read-card/",
            {
                "dev_index": "IDX-READ-SERIAL-FALLBACK",
                "timeout_seconds": 2,
                "poll_interval_ms": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["card_no"], "CARD-NEW-39")
        self.assertEqual(payload["serial_no"], 39)
        self.assertGreaterEqual(mock_client.acs_event_search.call_count, 4)
        mock_sleep.assert_called()


class HikCatchupServiceTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant Catchup", code="tenant-catchup")
        self.gateway = Gateway.objects.create(
            tenant=self.tenant,
            base_url="https://gw-catchup.local",
            username="admin",
            password="pass",
        )
        self.device = Device.objects.create(
            gateway=self.gateway,
            tenant=self.tenant,
            serial_number="SN-CATCHUP",
            dev_index="IDX-CATCHUP",
            status="online",
        )

    @patch("hik_gateway.services.catchup.ingest_acs_event")
    @patch("hik_gateway.services.catchup.get_shared_gateway_client")
    def test_initial_catchup_uses_full_history_window(self, mock_get_client, mock_ingest):
        from hik_gateway.services.catchup import catchup_device

        mock_client = mock_get_client.return_value
        mock_client.acs_event_search.side_effect = [
            {
                "AcsEventTotalNum": {
                    "totalMatches": 1,
                    "InfoList": [{"serialNo": "1", "dateTime": "2026-01-01T08:00:00Z"}],
                }
            },
            {"AcsEventTotalNum": {"totalMatches": 0, "InfoList": []}},
        ]
        mock_ingest.return_value = (None, None)

        processed = catchup_device(self.device, max_results=50)

        self.assertEqual(processed, 0)
        first_call_condition = mock_client.acs_event_search.call_args_list[0].args[1]
        self.assertEqual(first_call_condition["AcsEventCond"]["startTime"], "1970-01-01T00:00:00+00:00")

    @patch("hik_gateway.services.catchup.ingest_acs_event")
    @patch("hik_gateway.services.catchup.get_shared_gateway_client")
    def test_catchup_counts_all_returned_events(self, mock_get_client, mock_ingest):
        from hik_gateway.services.catchup import catchup_device

        mock_client = mock_get_client.return_value
        mock_client.acs_event_search.side_effect = [
            {
                "AcsEventTotalNum": {
                    "totalMatches": 2,
                    "InfoList": [
                        {"serialNo": "10", "dateTime": "2026-01-01T08:00:00Z"},
                        {"serialNo": "11", "dateTime": "2026-01-01T08:01:00Z"},
                    ],
                }
            },
            {"AcsEventTotalNum": {"totalMatches": 0, "InfoList": []}},
        ]
        from types import SimpleNamespace

        mock_ingest.side_effect = [
            (SimpleNamespace(serial_no=10, event_datetime=datetime(2026, 1, 1, 8, 0, tzinfo=dt_timezone.utc)), None),
            (SimpleNamespace(serial_no=11, event_datetime=datetime(2026, 1, 1, 8, 1, tzinfo=dt_timezone.utc)), None),
        ]

        processed = catchup_device(self.device, max_results=50)

        self.assertEqual(processed, 2)

    @patch("hik_gateway.services.catchup.ingest_acs_event")
    @patch("hik_gateway.services.catchup.get_shared_gateway_client")
    def test_catchup_supports_acs_event_response_shape(self, mock_get_client, mock_ingest):
        from hik_gateway.services.catchup import catchup_device
        from types import SimpleNamespace

        mock_client = mock_get_client.return_value
        mock_client.acs_event_search.side_effect = [
            {
                "AcsEvent": {
                    "InfoList": [{"serialNo": 20, "time": "2026-01-01T08:00:00Z", "major": 2, "minor": 1}],
                }
            },
            {"AcsEvent": {"InfoList": []}},
        ]
        mock_ingest.side_effect = [
            (SimpleNamespace(serial_no=20, event_datetime=datetime(2026, 1, 1, 8, 0, tzinfo=dt_timezone.utc)), None),
        ]

        processed = catchup_device(self.device, max_results=50)

        self.assertEqual(processed, 1)

    @patch("hik_gateway.services.catchup.ingest_acs_event")
    @patch("hik_gateway.services.catchup.get_shared_gateway_client")
    def test_catchup_falls_back_without_time_window_when_gateway_rejects_window(self, mock_get_client, mock_ingest):
        from hik_gateway.services.catchup import catchup_device
        from types import SimpleNamespace

        mock_client = mock_get_client.return_value
        mock_client.acs_event_search.side_effect = [
            requests.HTTPError("400 badJsonContent Wrong JSON content"),
            {
                "AcsEvent": {
                    "InfoList": [{"serialNo": 21, "time": "2026-01-01T08:00:00Z", "major": 2, "minor": 1}],
                }
            },
        ]
        mock_ingest.side_effect = [
            (SimpleNamespace(serial_no=21, event_datetime=datetime(2026, 1, 1, 8, 0, tzinfo=dt_timezone.utc)), None),
        ]

        processed = catchup_device(self.device, max_results=50)

        self.assertEqual(processed, 1)
        first_call_payload = mock_client.acs_event_search.call_args_list[0].args[1]
        second_call_payload = mock_client.acs_event_search.call_args_list[1].args[1]
        self.assertIn("startTime", first_call_payload["AcsEventCond"])
        self.assertNotIn("startTime", second_call_payload["AcsEventCond"])


class HikDeviceSyncServiceTests(APITestCase):
    @patch("hik_gateway.services.device_sync.get_shared_gateway_client")
    def test_sync_gateway_devices_creates_settings_gateway_and_links_device(self, mock_get_client):
        from hik_gateway.services.device_sync import sync_gateway_devices

        tenant = Tenant.objects.create(name="Tenant Settings Gateway", code="tenant-settings-gw")
        mock_get_client.return_value.device_list_all.return_value = {
            "SearchResult": {
                "MatchList": [
                    {
                        "Device": {
                            "EhomeParams": {"EhomeID": "SN-SETTINGS"},
                            "devIndex": "IDX-SETTINGS",
                            "devName": "Settings Reader",
                            "devStatus": "online",
                            "protocolType": "ehomeV5",
                        }
                    }
                ]
            }
        }

        with self.settings(
            HIK_DEVICE_GATEWAY_BASE_URL="https://shared-gw.local",
            HIK_DEVICE_GATEWAY_USERNAME="admin",
            HIK_DEVICE_GATEWAY_PASSWORD="pass",
        ):
            synced = sync_gateway_devices(tenant)

        self.assertEqual(synced, 1)
        gateway = Gateway.objects.get(tenant=tenant)
        device = Device.objects.get(tenant=tenant, dev_index="IDX-SETTINGS")
        self.assertEqual(device.gateway, gateway)

    @patch("hik_gateway.services.device_sync.sync_gateway_devices")
    def test_sync_all_gateways_uses_gateway_tenants_even_without_devices(self, mock_sync):
        from hik_gateway.services.device_sync import sync_all_gateways

        t1 = Tenant.objects.create(name="Tenant Sync 1", code="tenant-sync-1")
        t2 = Tenant.objects.create(name="Tenant Sync 2", code="tenant-sync-2")
        Gateway.objects.create(tenant=t1, base_url="https://gw-sync-1.local", username="admin", password="pass")
        Gateway.objects.create(tenant=t2, base_url="https://gw-sync-2.local", username="admin", password="pass")

        mock_sync.side_effect = [2, 3]

        total = sync_all_gateways()

        self.assertEqual(total, 5)
        self.assertEqual(mock_sync.call_count, 2)
        called_tenants = {call.args[0].code for call in mock_sync.call_args_list}
        self.assertEqual(called_tenants, {"tenant-sync-1", "tenant-sync-2"})

    @patch("hik_gateway.services.device_sync.sync_gateway_devices")
    def test_sync_all_gateways_falls_back_to_all_tenants_with_settings_gateway(self, mock_sync):
        from hik_gateway.services.device_sync import sync_all_gateways

        Tenant.objects.create(name="Tenant Settings 1", code="tenant-settings-1")
        Tenant.objects.create(name="Tenant Settings 2", code="tenant-settings-2")

        mock_sync.side_effect = [1, 4]

        total = sync_all_gateways()

        self.assertEqual(total, 5)
        self.assertEqual(mock_sync.call_count, 2)
        called_tenants = {call.args[0].code for call in mock_sync.call_args_list}
        self.assertEqual(called_tenants, {"tenant-settings-1", "tenant-settings-2"})
