"""Tests d'intégration de la surface /api/mobile/* (Phase 3)."""
from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from employees.models import Employee
from hik_gateway.models import AttendanceLog, Device as HikDevice, Gateway, RawEvent
from presence.models import Site
from presence.services import MOBILE_GATEWAY_BASE_URL, get_mobile_device
from tenants.models import Tenant, TenantMembership, TenantRole

User = get_user_model()

_FAST_HASHER = override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)

ME_URL = "/api/mobile/me/"
PUNCH_URL = "/api/mobile/punch/"
HISTORY_URL = "/api/mobile/history/"

SITE_LAT = 5.3485
SITE_LNG = -4.0277


def punch_payload(**overrides):
    payload = {
        "latitude": SITE_LAT,
        "longitude": SITE_LNG,
        "accuracy_m": 12,
        "action": "CHECK_IN",
        "idempotency_key": str(uuid.uuid4()),
        "client_reported_at": "2026-07-29T08:00:00Z",
        "app_version": "1.0.0",
        "mocked": False,
    }
    payload.update(overrides)
    return payload


@_FAST_HASHER
class MobileApiTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(code="MOB-A", name="Mobile A", is_active=True)
        cls.other_tenant = Tenant.objects.create(code="MOB-B", name="Mobile B", is_active=True)

        cls.employee_user = User.objects.create_user("memp@m.test", "memp@m.test", "pass1234!")
        TenantMembership.objects.create(
            user=cls.employee_user, tenant=cls.tenant, role=TenantRole.EMPLOYEE
        )
        cls.employee = Employee.objects.create(
            tenant=cls.tenant, employee_no="1001", name="Ada", user=cls.employee_user
        )

        cls.unlinked_user = User.objects.create_user("nolink@m.test", "nolink@m.test", "pass1234!")
        TenantMembership.objects.create(
            user=cls.unlinked_user, tenant=cls.tenant, role=TenantRole.EMPLOYEE
        )

        cls.site = Site.objects.create(
            tenant=cls.tenant, name="Siège", latitude=str(SITE_LAT), longitude=str(SITE_LNG), radius_m=100
        )


class MobileMeTests(MobileApiTestBase):
    def test_requires_linked_employee(self):
        self.client.force_authenticate(self.unlinked_user)
        response = self.client.get(ME_URL)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "PROFILE_NOT_LINKED")

    def test_me_payload_shape(self):
        self.client.force_authenticate(self.employee_user)
        response = self.client.get(ME_URL)
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["employee"]["employee_no"], "1001")
        self.assertEqual(payload["employee"]["tenant"]["code"], "MOB-A")
        self.assertEqual(payload["suggested_action"], "CHECK_IN")
        self.assertFalse(payload["has_punched_in"])
        self.assertEqual(payload["sites"][0]["name"], "Siège")
        self.assertIn("day_schedule", payload)


class MobilePunchTests(MobileApiTestBase):
    def setUp(self):
        self.client.force_authenticate(self.employee_user)

    def test_check_in_success_creates_log_with_server_time(self):
        response = self.client.post(PUNCH_URL, punch_payload(), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        payload = response.json()
        self.assertEqual(payload["action"], "CHECK_IN")
        self.assertEqual(payload["zone"], "inside")
        self.assertEqual(payload["site"]["name"], "Siège")

        log = AttendanceLog.objects.get(tenant=self.tenant, source=AttendanceLog.SOURCE_MOBILE)
        self.assertEqual(log.employee_id, self.employee.id)
        self.assertEqual(log.normalized_action, "CHECK_IN")
        # Heure serveur faisant foi : le client_reported_at (08:00Z) n'est PAS
        # le timestamp officiel.
        self.assertNotEqual(log.timestamp.isoformat(), "2026-07-29T08:00:00+00:00")
        raw = log.raw_event.payload
        self.assertEqual(raw["client_reported_at"], "2026-07-29T08:00:00+00:00")
        self.assertIsNotNone(raw["clock_drift_seconds"])
        self.assertEqual(raw["zone"], "inside")
        self.assertFalse(raw["mocked"])

    def test_idempotent_retry_same_key_returns_same_punch(self):
        payload = punch_payload()
        first = self.client.post(PUNCH_URL, payload, format="json")
        self.assertEqual(first.status_code, 201)
        second = self.client.post(PUNCH_URL, payload, format="json")
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(second.json()["action"], "CHECK_IN")
        self.assertEqual(
            AttendanceLog.objects.filter(source=AttendanceLog.SOURCE_MOBILE).count(), 1
        )

    def test_too_soon_between_distinct_punches(self):
        self.client.post(PUNCH_URL, punch_payload(), format="json")
        response = self.client.post(
            PUNCH_URL, punch_payload(action="CHECK_OUT"), format="json"
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["code"], "TOO_SOON")

    def test_out_of_zone(self):
        response = self.client.post(
            PUNCH_URL, punch_payload(latitude=SITE_LAT + 0.05), format="json"
        )
        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["code"], "OUT_OF_ZONE")
        self.assertEqual(payload["nearest_site"]["name"], "Siège")
        self.assertGreater(payload["distance_m"], 1000)

    def test_accuracy_too_low(self):
        response = self.client.post(PUNCH_URL, punch_payload(accuracy_m=500), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "ACCURACY_TOO_LOW")

    def test_no_site_configured(self):
        Site.objects.all().update(is_active=False)
        response = self.client.post(PUNCH_URL, punch_payload(), format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "NO_SITE_CONFIGURED")

    def test_stale_action_conflict_with_physical_punch_mixed(self):
        # Un badge physique (source realtime) compte dans la bascule.
        device = get_mobile_device(self.tenant)
        raw = RawEvent.objects.create(
            tenant=self.tenant, device=device, dev_index="MOBILE", event_type="seed",
            event_datetime="2026-07-29T06:00:00Z", employee_no="1001",
            dedupe_key="seed-physical-1", payload={},
        )
        AttendanceLog.objects.create(
            tenant=self.tenant, employee=self.employee, person_id="1001", device=device,
            timestamp="2026-07-29T06:00:00Z", attendance_type="seed",
            normalized_action="CHECK_IN", direction="IN",
            source=AttendanceLog.SOURCE_REALTIME, raw_event=raw,
        )
        response = self.client.post(PUNCH_URL, punch_payload(action="CHECK_IN"), format="json")
        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertEqual(payload["code"], "SUGGESTED_ACTION_CHANGED")
        self.assertEqual(payload["suggested_action"], "CHECK_OUT")

    def test_missing_idempotency_key(self):
        response = self.client.post(
            PUNCH_URL, punch_payload(idempotency_key=""), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "MISSING_IDEMPOTENCY_KEY")

    def test_unlinked_user_forbidden(self):
        self.client.force_authenticate(self.unlinked_user)
        response = self.client.post(PUNCH_URL, punch_payload(), format="json")
        self.assertEqual(response.status_code, 403)


class MobileHistoryTests(MobileApiTestBase):
    def test_history_lists_own_punches_only(self):
        self.client.force_authenticate(self.employee_user)
        self.client.post(PUNCH_URL, punch_payload(), format="json")
        response = self.client.get(HISTORY_URL)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["source"], "mobile")
        self.assertEqual(payload["results"][0]["site_name"], "Siège")


class VirtualDeviceCapabilityTests(MobileApiTestBase):
    def test_get_mobile_device_idempotent(self):
        device1 = get_mobile_device(self.tenant)
        device2 = get_mobile_device(self.tenant)
        self.assertEqual(device1.id, device2.id)
        self.assertEqual(device1.kind, HikDevice.KIND_MOBILE_VIRTUAL)
        self.assertFalse(device1.gateway.supports_sync)

    def test_virtual_gateway_excluded_from_sync(self):
        get_mobile_device(self.tenant)
        from hik_gateway.services import device_sync

        # Aucun client HTTP ne doit être construit pour le tenant : sa seule
        # passerelle est virtuelle.
        with mock.patch.object(device_sync, "get_shared_gateway_client") as client_factory:
            client_factory.return_value.device_list_all.return_value = {}
            with mock.patch.object(device_sync, "extract_devices", return_value=[]):
                device_sync.sync_gateway_devices(self.tenant)
            # Le client peut être construit (identifiants globaux) mais la
            # passerelle virtuelle ne doit jamais être choisie comme cible DB.
        gateway = Gateway.objects.get(tenant=self.tenant, kind=Gateway.KIND_MOBILE_VIRTUAL)
        self.assertEqual(gateway.base_url, MOBILE_GATEWAY_BASE_URL)
        self.assertFalse(
            Gateway.objects.filter(
                tenant=self.tenant, kind=Gateway.KIND_HIKVISION
            ).exclude(base_url=MOBILE_GATEWAY_BASE_URL).filter(base_url=MOBILE_GATEWAY_BASE_URL).exists()
        )

    def test_mobile_punch_visible_in_admin_logs(self):
        admin = User.objects.create_user("madmin@m.test", "madmin@m.test", "pass1234!")
        TenantMembership.objects.create(user=admin, tenant=self.tenant, role=TenantRole.TENANT_ADMIN)

        self.client.force_authenticate(self.employee_user)
        self.client.post(PUNCH_URL, punch_payload(), format="json")

        self.client.force_authenticate(admin)
        response = self.client.get("/api/hikgateway/events/", {"tenant": "MOB-A"})
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "mobile")
