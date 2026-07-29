"""Verrou de sécurité du rôle « employee » (app mobile).

Un compte au rôle employee ne doit accéder à AUCUNE donnée du tenant via les
endpoints d'administration. Le test-balai s'auto-génère depuis le routeur DRF :
toute nouvelle route enregistrée sans classification explicite fait échouer la
suite — impossible d'ajouter un ViewSet en oubliant le verrou.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from config.api_urls import router
from devices.models import Device
from employees.models import Employee, Organization, Planning, WorkShift
from tenants.models import Tenant, TenantMembership, TenantRole

User = get_user_model()

_FAST_HASHER = override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)

# Classification de CHAQUE préfixe du routeur pour un compte employee.
# "empty"  : la liste répond 200 avec zéro résultat (scoping par tenant admin)
# "forbidden" : la liste répond 403
# Ajouter ici toute nouvelle route — le test échoue sinon.
ROUTER_EXPECTATIONS: dict[str, str] = {
    "tenants": "empty",
    "devices": "empty",
    "device-onboarding-jobs": "empty",
    "events": "empty",
    "employees": "empty",
    "organizations": "empty",
    "departments": "empty",
    "plannings": "empty",
    "planning-assignments": "empty",
    "work-shifts": "empty",
    "access-groups": "empty",
    "leave-requests": "empty",
}

# Endpoints hors routeur qui doivent refuser un compte employee.
FORBIDDEN_FUNCTION_ENDPOINTS = [
    "/api/hikgateway/events/?tenant=GATE-A",
    "/api/hikgateway/reports/attendance/?tenant=GATE-A",
    "/api/home/summary/?tenant=GATE-A",
    "/api/audit/events/?tenant=GATE-A",
]


@_FAST_HASHER
class EmployeeRoleGateTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(code="GATE-A", name="Gate A", is_active=True)
        cls.other_tenant = Tenant.objects.create(code="GATE-B", name="Gate B", is_active=True)

        cls.employee_user = User.objects.create_user("emp@gate.test", "emp@gate.test", "pass1234!")
        TenantMembership.objects.create(
            user=cls.employee_user, tenant=cls.tenant, role=TenantRole.EMPLOYEE
        )

        cls.viewer_user = User.objects.create_user("viewer@gate.test", "viewer@gate.test", "pass1234!")
        TenantMembership.objects.create(
            user=cls.viewer_user, tenant=cls.tenant, role=TenantRole.VIEWER
        )

        # Employé en A + viewer en B : ne doit voir QUE B.
        cls.mixed_user = User.objects.create_user("mixed@gate.test", "mixed@gate.test", "pass1234!")
        TenantMembership.objects.create(
            user=cls.mixed_user, tenant=cls.tenant, role=TenantRole.EMPLOYEE
        )
        TenantMembership.objects.create(
            user=cls.mixed_user, tenant=cls.other_tenant, role=TenantRole.VIEWER
        )

        # Données réelles dans le tenant A : elles ne doivent jamais fuiter.
        org = Organization.objects.create(tenant=cls.tenant, name="Org A", code="ORGA")
        Employee.objects.create(tenant=cls.tenant, employee_no="E-1", name="Ada")
        Planning.objects.create(tenant=cls.tenant, name="P1", code="P1")
        WorkShift.objects.create(tenant=cls.tenant, name="Day")
        Device.objects.create(
            tenant=cls.tenant, serial_number="SN-GATE-1", dev_index="gate-dev-1", name="Door"
        )
        Organization.objects.create(tenant=cls.other_tenant, name="Org B", code="ORGB")
        Employee.objects.create(tenant=cls.other_tenant, employee_no="B-1", name="Bea")

    def _list_len(self, payload) -> int:
        if isinstance(payload, dict) and "results" in payload:
            return len(payload["results"])
        if isinstance(payload, list):
            return len(payload)
        return -1

    def test_every_router_route_is_classified(self):
        registered = {prefix for prefix, viewset, basename in router.registry}
        unclassified = registered - set(ROUTER_EXPECTATIONS)
        self.assertFalse(
            unclassified,
            "Routes du routeur sans classification employee (compléter "
            f"ROUTER_EXPECTATIONS dans {__name__}): {sorted(unclassified)}",
        )

    def test_employee_sees_nothing_on_router_lists(self):
        self.client.force_authenticate(self.employee_user)
        for prefix, expectation in ROUTER_EXPECTATIONS.items():
            with self.subTest(route=prefix):
                response = self.client.get(f"/api/{prefix}/")
                if expectation == "empty":
                    self.assertEqual(response.status_code, 200, response.content)
                    self.assertEqual(
                        self._list_len(response.json()), 0,
                        f"/api/{prefix}/ a fuité des données à un compte employee",
                    )
                else:
                    self.assertEqual(response.status_code, 403, response.content)

    def test_employee_forbidden_on_function_endpoints(self):
        self.client.force_authenticate(self.employee_user)
        for url in FORBIDDEN_FUNCTION_ENDPOINTS:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403, f"{url} → {response.status_code}")

    def test_employee_cannot_resolve_billing_tenant(self):
        self.client.force_authenticate(self.employee_user)
        response = self.client.get("/api/billing/summary/", HTTP_X_TENANT_CODE="GATE-A")
        self.assertEqual(response.status_code, 403, response.content)

    def test_mixed_user_sees_only_admin_tenant(self):
        self.client.force_authenticate(self.mixed_user)
        response = self.client.get("/api/employees/")
        rows = response.json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        self.assertEqual([row["employee_no"] for row in rows], ["B-1"])

    def test_viewer_regression_still_sees_data(self):
        self.client.force_authenticate(self.viewer_user)
        response = self.client.get("/api/employees/")
        rows = response.json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        self.assertEqual(len(rows), 1)

    def test_login_still_returns_employee_membership(self):
        # L'app mobile a besoin de voir le tenant dans la réponse de login.
        response = self.client.post(
            "/api/auth/login/",
            {"identifier": "emp@gate.test", "password": "pass1234!"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        roles = [t["role"] for t in response.json()["tenants"]]
        self.assertEqual(roles, [TenantRole.EMPLOYEE])
