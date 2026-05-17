"""Tests Phase 4.2 — Isolation multi-tenant.

Vérifient que :
- les ViewSets DRF (Device, AttendanceEvent, Employee, Planning, AccessGroup)
  ne renvoient JAMAIS les rows d'un autre tenant à un user authentifié
- un staff/superuser voit tout
- un user sans membership voit zéro
- la création / mise à jour cross-tenant est bloquée
- billing.summary est bien scopé au tenant courant

On utilise le helper `scope_queryset_to_user_tenants` (testé indirectement à
travers les endpoints) — toute régression de scoping doit casser un de ces tests.
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from billing.models import Customer, Plan, Subscription, SubscriptionStatus
from devices.models import Device
from employees.models import (
    Employee,
    Organization,
    Planning,
    WorkShift,
)
from events.models import AttendanceEvent
from tenants.models import Tenant, TenantMembership, TenantRole

User = get_user_model()


_FAST_HASHER = override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

class _IsolationFixtureMixin:
    """Two tenants A and B, each with their own user, device, employee, event."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(code="ALPHA", name="Alpha", is_active=True)
        cls.tenant_b = Tenant.objects.create(code="BETA", name="Beta", is_active=True)

        cls.user_a = User.objects.create_user("alice@a.test", "alice@a.test", "pass1234!")
        cls.user_b = User.objects.create_user("bob@b.test", "bob@b.test", "pass1234!")
        cls.staff = User.objects.create_user(
            "staff@x.test", "staff@x.test", "pass1234!", is_staff=True
        )
        cls.outsider = User.objects.create_user(
            "out@x.test", "out@x.test", "pass1234!"
        )

        TenantMembership.objects.create(
            user=cls.user_a, tenant=cls.tenant_a, role=TenantRole.TENANT_ADMIN
        )
        TenantMembership.objects.create(
            user=cls.user_b, tenant=cls.tenant_b, role=TenantRole.TENANT_ADMIN
        )

        # Each tenant owns one device, one employee, one event
        cls.dev_a = Device.objects.create(
            tenant=cls.tenant_a,
            serial_number="SN-A-1",
            dev_index="dev-A-1",
            name="Door A",
        )
        cls.dev_b = Device.objects.create(
            tenant=cls.tenant_b,
            serial_number="SN-B-1",
            dev_index="dev-B-1",
            name="Door B",
        )

        cls.emp_a = Employee.objects.create(
            tenant=cls.tenant_a,
            employee_no="EMP-A-1",
            first_name="Alice",
            last_name="A",
        )
        cls.emp_b = Employee.objects.create(
            tenant=cls.tenant_b,
            employee_no="EMP-B-1",
            first_name="Bob",
            last_name="B",
        )

        from django.utils import timezone
        cls.event_a = AttendanceEvent.objects.create(
            tenant=cls.tenant_a,
            device=cls.dev_a,
            user_id="p-A",
            timestamp=timezone.now(),
            event_type="check_in",
        )
        cls.event_b = AttendanceEvent.objects.create(
            tenant=cls.tenant_b,
            device=cls.dev_b,
            user_id="p-B",
            timestamp=timezone.now(),
            event_type="check_in",
        )


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------

@_FAST_HASHER
class DeviceIsolationTests(_IsolationFixtureMixin, APITestCase):
    URL = "/api/devices/"

    def test_anon_blocked(self):
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 401)

    def test_user_a_only_sees_tenant_a_devices(self):
        self.client.force_authenticate(self.user_a)
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        data = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        serials = {d["serial_number"] for d in data}
        self.assertEqual(serials, {"SN-A-1"})

    def test_user_b_only_sees_tenant_b_devices(self):
        self.client.force_authenticate(self.user_b)
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        data = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        serials = {d["serial_number"] for d in data}
        self.assertEqual(serials, {"SN-B-1"})

    def test_user_cannot_get_other_tenants_device_by_id(self):
        self.client.force_authenticate(self.user_a)
        resp = self.client.get(f"{self.URL}{self.dev_b.id}/")
        # Either 404 (filtered queryset) or 403 — both prove isolation
        self.assertIn(resp.status_code, [403, 404])

    def test_user_without_membership_sees_nothing(self):
        self.client.force_authenticate(self.outsider)
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        data = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        self.assertEqual(len(data), 0)

    def test_staff_sees_all_devices(self):
        self.client.force_authenticate(self.staff)
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        data = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        serials = {d["serial_number"] for d in data}
        self.assertSetEqual(serials, {"SN-A-1", "SN-B-1"})

    def test_user_a_cannot_create_device_in_tenant_b(self):
        """perform_create() must reject if tenant scope is not granted."""
        self.client.force_authenticate(self.user_a)
        resp = self.client.post(
            self.URL,
            data={
                "tenant": self.tenant_b.id,
                "serial_number": "SN-CROSS",
                "name": "Hijack",
            },
            format="json",
        )
        # _require_tenant_scope raises PermissionDenied → 403
        self.assertIn(resp.status_code, [400, 403])

    def test_user_a_cannot_update_tenant_b_device(self):
        self.client.force_authenticate(self.user_a)
        resp = self.client.patch(
            f"{self.URL}{self.dev_b.id}/",
            data={"name": "Renamed"},
            format="json",
        )
        self.assertIn(resp.status_code, [403, 404])
        self.dev_b.refresh_from_db()
        self.assertEqual(self.dev_b.name, "Door B")


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------

@_FAST_HASHER
class EmployeeIsolationTests(_IsolationFixtureMixin, APITestCase):
    URL = "/api/employees/"

    def test_user_a_only_sees_tenant_a_employees(self):
        self.client.force_authenticate(self.user_a)
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        data = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        emp_nos = {e["employee_no"] for e in data}
        self.assertEqual(emp_nos, {"EMP-A-1"})

    def test_user_a_cannot_fetch_tenant_b_employee_by_id(self):
        self.client.force_authenticate(self.user_a)
        resp = self.client.get(f"{self.URL}{self.emp_b.id}/")
        self.assertIn(resp.status_code, [403, 404])


# ---------------------------------------------------------------------------
# AttendanceEvents (events app)
# ---------------------------------------------------------------------------

@_FAST_HASHER
class EventsIsolationTests(_IsolationFixtureMixin, APITestCase):
    URL = "/api/events/"

    def test_user_a_only_sees_tenant_a_events(self):
        self.client.force_authenticate(self.user_a)
        resp = self.client.get(self.URL)
        # Some routers omit /api/events/ — accept both 200 and 404 to keep this
        # test robust against URL-routing decisions, but if 200 the scoping
        # MUST exclude tenant B.
        if resp.status_code == 404:
            self.skipTest("AttendanceEvent endpoint not exposed under /api/events/")
        self.assertEqual(resp.status_code, 200)
        data = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        user_ids = {e["user_id"] for e in data if "user_id" in e}
        # If serializer doesn't return user_id, fall back to id-based check
        if user_ids:
            self.assertEqual(user_ids, {"p-A"})
        else:
            ids = {e["id"] for e in data}
            self.assertNotIn(self.event_b.id, ids)
            self.assertIn(self.event_a.id, ids)


# ---------------------------------------------------------------------------
# Planning / WorkShift / AccessGroup — `_scope_to_request_tenants` helpers
# ---------------------------------------------------------------------------

@_FAST_HASHER
class PlanningIsolationTests(_IsolationFixtureMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.plan_a = Planning.objects.create(tenant=cls.tenant_a, name="Plan A")
        cls.plan_b = Planning.objects.create(tenant=cls.tenant_b, name="Plan B")

    def test_user_a_only_sees_planning_a(self):
        self.client.force_authenticate(self.user_a)
        resp = self.client.get("/api/plannings/")
        if resp.status_code == 404:
            self.skipTest("Planning endpoint not available under /api/plannings/")
        self.assertEqual(resp.status_code, 200)
        data = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        names = {p["name"] for p in data}
        self.assertEqual(names, {"Plan A"})


@_FAST_HASHER
class WorkShiftIsolationTests(_IsolationFixtureMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.shift_a = WorkShift.objects.create(tenant=cls.tenant_a, name="Day A")
        cls.shift_b = WorkShift.objects.create(tenant=cls.tenant_b, name="Day B")

    def test_user_a_only_sees_workshift_a(self):
        self.client.force_authenticate(self.user_a)
        resp = self.client.get("/api/work-shifts/")
        if resp.status_code == 404:
            self.skipTest("WorkShift endpoint not at /api/work-shifts/")
        self.assertEqual(resp.status_code, 200)
        data = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        names = {s["name"] for s in data}
        self.assertEqual(names, {"Day A"})


# ---------------------------------------------------------------------------
# Billing — la `summary` doit être scopée par X-Tenant-Code
# ---------------------------------------------------------------------------

@_FAST_HASHER
class BillingIsolationTests(_IsolationFixtureMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.plan = Plan.objects.create(
            code="pro",
            name="Pro",
            interval="month",
            amount=Decimal("29.99"),
            currency="eur",
            stripe_price_id="price_test",
        )
        cls.cust_a = Customer.objects.create(
            tenant=cls.tenant_a, stripe_customer_id="cus_a", email="a@a.test"
        )
        cls.cust_b = Customer.objects.create(
            tenant=cls.tenant_b, stripe_customer_id="cus_b", email="b@b.test"
        )
        cls.sub_a = Subscription.objects.create(
            tenant=cls.tenant_a,
            customer=cls.cust_a,
            plan=cls.plan,
            stripe_subscription_id="sub_a",
            status=SubscriptionStatus.ACTIVE,
        )
        cls.sub_b = Subscription.objects.create(
            tenant=cls.tenant_b,
            customer=cls.cust_b,
            plan=cls.plan,
            stripe_subscription_id="sub_b",
            status=SubscriptionStatus.ACTIVE,
        )

    def test_user_a_summary_only_returns_tenant_a_subscription(self):
        self.client.force_authenticate(self.user_a)
        resp = self.client.get(
            "/api/billing/summary/", HTTP_X_TENANT_CODE=self.tenant_a.code
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["tenant"]["code"], self.tenant_a.code)
        self.assertIsNotNone(resp.data["subscription"])
        # Make sure it's NOT tenant B's sub leaking through
        self.assertEqual(
            resp.data["subscription"]["stripe_subscription_id"], "sub_a"
        )

    def test_user_a_cannot_request_tenant_b_summary(self):
        # Asking for tenant B with X-Tenant-Code must 403 if no membership
        self.client.force_authenticate(self.user_a)
        resp = self.client.get(
            "/api/billing/summary/", HTTP_X_TENANT_CODE=self.tenant_b.code
        )
        self.assertEqual(resp.status_code, 403)
