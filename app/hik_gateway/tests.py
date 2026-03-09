from datetime import datetime
from datetime import timezone as dt_timezone
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
        raw_event = RawEvent.objects.create(
            tenant=self.tenant,
            device=self.device,
            dev_index=self.device.dev_index,
            event_type="AccessControllerEvent",
            event_datetime="2026-02-01T08:00:00Z",
            major_event_type=5,
            sub_event_type=1,
            serial_no=100,
            dedupe_key="event-100",
            payload={"sample": True},
        )
        AttendanceLog.objects.create(
            tenant=self.tenant,
            person_id="E1001",
            device=self.device,
            timestamp="2026-02-01T08:00:00Z",
            attendance_type="checkin",
            attendance_status="checkin",
            direction="IN",
            source=AttendanceLog.SOURCE_REALTIME,
            raw_event=raw_event,
        )

        response = self.client.get(
            "/api/hikgateway/events/",
            {"tenant": self.tenant.code, "source": "realtime", "dev_index": self.device.dev_index},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["person_id"], "E1001")
        self.assertEqual(payload["results"][0]["device"]["dev_index"], self.device.dev_index)


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
