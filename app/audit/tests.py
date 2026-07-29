"""Tests de l'API d'audit et de l'instrumentation AuditLogMixin."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from audit.models import AuditEvent
from employees.models import WorkShift
from tenants.models import Tenant, TenantMembership, TenantRole

User = get_user_model()

_FAST_HASHER = override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)


class _AuditFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(code="AUD-A", name="Audit A", is_active=True)
        cls.tenant_b = Tenant.objects.create(code="AUD-B", name="Audit B", is_active=True)

        cls.admin_a = User.objects.create_user("aud-admin@a.test", "aud-admin@a.test", "pass1234!")
        cls.viewer_a = User.objects.create_user("aud-viewer@a.test", "aud-viewer@a.test", "pass1234!")
        cls.user_b = User.objects.create_user("aud-user@b.test", "aud-user@b.test", "pass1234!")
        cls.staff = User.objects.create_user(
            "aud-staff@x.test", "aud-staff@x.test", "pass1234!", is_staff=True
        )

        TenantMembership.objects.create(
            user=cls.admin_a, tenant=cls.tenant_a, role=TenantRole.TENANT_ADMIN
        )
        TenantMembership.objects.create(
            user=cls.viewer_a, tenant=cls.tenant_a, role=TenantRole.VIEWER
        )
        TenantMembership.objects.create(
            user=cls.user_b, tenant=cls.tenant_b, role=TenantRole.TENANT_ADMIN
        )

        AuditEvent.objects.create(
            actor=cls.admin_a,
            action="create_employee",
            target_model="Employee",
            target_id="1",
            tenant_code="AUD-A",
        )
        AuditEvent.objects.create(
            actor=cls.user_b,
            action="delete_device",
            target_model="Device",
            target_id="9",
            tenant_code="AUD-B",
        )


@_FAST_HASHER
class AuditEventsApiTests(_AuditFixtureMixin, APITestCase):
    url = "/api/audit/events/"

    def test_requires_authentication(self):
        response = self.client.get(self.url, {"tenant": "AUD-A"})
        self.assertEqual(response.status_code, 401)

    def test_requires_tenant_param_for_non_staff(self):
        self.client.force_authenticate(self.admin_a)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 400)

    def test_unknown_tenant_404(self):
        self.client.force_authenticate(self.admin_a)
        response = self.client.get(self.url, {"tenant": "NOPE"})
        self.assertEqual(response.status_code, 404)

    def test_viewer_role_is_insufficient(self):
        self.client.force_authenticate(self.viewer_a)
        response = self.client.get(self.url, {"tenant": "AUD-A"})
        self.assertEqual(response.status_code, 403)

    def test_cross_tenant_access_denied(self):
        self.client.force_authenticate(self.user_b)
        response = self.client.get(self.url, {"tenant": "AUD-A"})
        self.assertEqual(response.status_code, 403)

    def test_tenant_scoped_results(self):
        self.client.force_authenticate(self.admin_a)
        response = self.client.get(self.url, {"tenant": "AUD-A"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["tenant_code"], "AUD-A")
        self.assertEqual(payload["results"][0]["actor"]["username"], "aud-admin@a.test")

    def test_staff_sees_all_without_tenant(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["count"], 2)

    def test_action_filter(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get(self.url, {"action": "delete"})
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["action"], "delete_device")

    def test_before_id_cursor(self):
        self.client.force_authenticate(self.staff)
        first = self.client.get(self.url, {"limit": 1}).json()
        self.assertEqual(first["count"], 1)
        newest_id = first["results"][0]["id"]
        rest = self.client.get(self.url, {"before_id": newest_id}).json()
        self.assertTrue(all(row["id"] < newest_id for row in rest["results"]))


@_FAST_HASHER
class AuditLogMixinTests(_AuditFixtureMixin, APITestCase):
    def test_crud_writes_audit_events(self):
        self.client.force_authenticate(self.admin_a)

        response = self.client.post(
            "/api/work-shifts/",
            {
                "tenant": self.tenant_a.id,
                "name": "Matin",
                "start_time": "08:00",
                "end_time": "16:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        shift_id = response.json()["id"]
        create_event = AuditEvent.objects.filter(action="create_workshift").latest("id")
        self.assertEqual(create_event.tenant_code, "AUD-A")
        self.assertEqual(create_event.target_id, str(shift_id))
        self.assertEqual(create_event.actor, self.admin_a)

        response = self.client.patch(
            f"/api/work-shifts/{shift_id}/", {"name": "Matin v2"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(
            AuditEvent.objects.filter(action="update_workshift", target_id=str(shift_id)).exists()
        )

        response = self.client.delete(f"/api/work-shifts/{shift_id}/?force=true")
        self.assertIn(response.status_code, (200, 204), response.content)
        delete_event = AuditEvent.objects.filter(action="delete_workshift").latest("id")
        self.assertEqual(delete_event.target_id, str(shift_id))
        self.assertEqual(delete_event.target_model, "WorkShift")
        self.assertEqual(delete_event.tenant_code, "AUD-A")
        self.assertFalse(WorkShift.objects.filter(id=shift_id).exists())

    def test_login_writes_audit_event(self):
        response = self.client.post(
            "/api/auth/login/",
            {"identifier": "aud-admin@a.test", "password": "pass1234!"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        event = AuditEvent.objects.filter(action="login").latest("id")
        self.assertEqual(event.actor, self.admin_a)
        self.assertEqual(event.tenant_code, "AUD-A")


@_FAST_HASHER
class HomeSummaryScopeTests(_AuditFixtureMixin, APITestCase):
    url = "/api/home/summary/"

    def test_requires_tenant_for_non_staff(self):
        self.client.force_authenticate(self.admin_a)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 400)

    def test_cross_tenant_denied(self):
        self.client.force_authenticate(self.user_b)
        response = self.client.get(self.url, {"tenant": "AUD-A"})
        self.assertEqual(response.status_code, 403)

    def test_member_gets_scoped_summary(self):
        self.client.force_authenticate(self.viewer_a)
        response = self.client.get(self.url, {"tenant": "AUD-A"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tenant"], "AUD-A")

    def test_staff_can_query_globally(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)


@_FAST_HASHER
class EmployeeVisitorFilterTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from employees.models import Employee

        cls.tenant = Tenant.objects.create(code="VIS-A", name="Visitors", is_active=True)
        cls.user = User.objects.create_user("vis@a.test", "vis@a.test", "pass1234!")
        TenantMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role=TenantRole.TENANT_ADMIN
        )
        Employee.objects.create(
            tenant=cls.tenant, employee_no="E1", name="Employe Un", is_visitor=False
        )
        Employee.objects.create(
            tenant=cls.tenant, employee_no="V1", name="Visiteur Un", is_visitor=True
        )

    def test_visitor_filter(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/employees/", {"tenant": "VIS-A", "is_visitor": "1"})
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        self.assertEqual([row["employee_no"] for row in rows], ["V1"])

        response = self.client.get("/api/employees/", {"tenant": "VIS-A", "is_visitor": "0"})
        rows = response.json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        self.assertEqual([row["employee_no"] for row in rows], ["E1"])

    def test_no_filter_returns_everyone(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/employees/", {"tenant": "VIS-A"})
        rows = response.json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        self.assertEqual(len(rows), 2)
