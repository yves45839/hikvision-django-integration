"""Tests du CRUD des sites de pointage (Phase 2)."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from audit.models import AuditEvent
from presence.models import Site
from tenants.models import Tenant, TenantMembership, TenantRole

User = get_user_model()

_FAST_HASHER = override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)

URL = "/api/punch-sites/"


@_FAST_HASHER
class SiteCrudTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(code="SITE-A", name="Site A", is_active=True)
        cls.other_tenant = Tenant.objects.create(code="SITE-B", name="Site B", is_active=True)

        cls.org_admin = User.objects.create_user("sadmin@s.test", "sadmin@s.test", "pass1234!")
        TenantMembership.objects.create(user=cls.org_admin, tenant=cls.tenant, role=TenantRole.ORG_ADMIN)
        cls.operator = User.objects.create_user("soper@s.test", "soper@s.test", "pass1234!")
        TenantMembership.objects.create(user=cls.operator, tenant=cls.tenant, role=TenantRole.OPERATOR)
        cls.employee_user = User.objects.create_user("semp@s.test", "semp@s.test", "pass1234!")
        TenantMembership.objects.create(user=cls.employee_user, tenant=cls.tenant, role=TenantRole.EMPLOYEE)

        cls.site = Site.objects.create(
            tenant=cls.tenant, name="Siège", latitude="5.348500", longitude="-4.027700", radius_m=100
        )
        Site.objects.create(
            tenant=cls.other_tenant, name="Ailleurs", latitude="48.860000", longitude="2.350000"
        )

    def _payload(self, **overrides):
        payload = {
            "tenant": self.tenant.id,
            "name": "Entrepôt",
            "address": "Zone 4, Abidjan",
            "latitude": "5.300000",
            "longitude": "-4.010000",
            "radius_m": 150,
            "is_active": True,
        }
        payload.update(overrides)
        return payload

    def test_list_is_tenant_scoped(self):
        self.client.force_authenticate(self.org_admin)
        response = self.client.get(URL)
        names = [row["name"] for row in response.json()]
        self.assertEqual(names, ["Siège"])

    def test_other_tenant_site_is_404(self):
        other_site = Site.objects.get(name="Ailleurs")
        self.client.force_authenticate(self.org_admin)
        response = self.client.get(f"{URL}{other_site.id}/")
        self.assertEqual(response.status_code, 404)

    def test_create_requires_org_admin(self):
        self.client.force_authenticate(self.operator)
        response = self.client.post(URL, self._payload(), format="json")
        self.assertEqual(response.status_code, 403)

        self.client.force_authenticate(self.org_admin)
        response = self.client.post(URL, self._payload(), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(AuditEvent.objects.filter(action="create_site").exists())

    def test_employee_role_sees_nothing(self):
        self.client.force_authenticate(self.employee_user)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_validation_bounds(self):
        self.client.force_authenticate(self.org_admin)
        for field, value in [
            ("latitude", "95.0"),
            ("longitude", "-190.0"),
            ("radius_m", 10),
            ("radius_m", 5000),
        ]:
            with self.subTest(field=field, value=value):
                response = self.client.post(URL, self._payload(**{field: value}), format="json")
                self.assertEqual(response.status_code, 400, response.content)

    def test_update_and_delete_require_org_admin(self):
        self.client.force_authenticate(self.operator)
        response = self.client.patch(f"{URL}{self.site.id}/", {"radius_m": 200}, format="json")
        self.assertEqual(response.status_code, 403)

        self.client.force_authenticate(self.org_admin)
        response = self.client.patch(f"{URL}{self.site.id}/", {"radius_m": 200}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        response = self.client.delete(f"{URL}{self.site.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertTrue(AuditEvent.objects.filter(action="delete_site").exists())

    def test_unique_name_per_tenant(self):
        self.client.force_authenticate(self.org_admin)
        response = self.client.post(URL, self._payload(name="Siège"), format="json")
        self.assertEqual(response.status_code, 400)
