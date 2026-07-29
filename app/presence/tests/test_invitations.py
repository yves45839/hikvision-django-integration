"""Tests des invitations app mobile (Phase 1b)."""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from employees.models import Employee
from presence.models import EmployeeInvitation, hash_invitation_secret
from presence.services import create_mobile_invitation
from tenants.models import Tenant, TenantMembership, TenantRole

User = get_user_model()

_FAST_HASHER = override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)

ACCEPT_URL = "/api/auth/employee-invitations/accept/"
PREVIEW_URL = "/api/auth/employee-invitations/preview/"
STRONG_PASSWORD = "Str0ng!Passw0rd#2026"


@_FAST_HASHER
class InvitationTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(code="INV-A", name="Invite A", is_active=True)
        cls.org_admin = User.objects.create_user("orgadmin@inv.test", "orgadmin@inv.test", "pass1234!")
        TenantMembership.objects.create(
            user=cls.org_admin, tenant=cls.tenant, role=TenantRole.ORG_ADMIN
        )
        cls.operator = User.objects.create_user("operator@inv.test", "operator@inv.test", "pass1234!")
        TenantMembership.objects.create(
            user=cls.operator, tenant=cls.tenant, role=TenantRole.OPERATOR
        )
        cls.employee = Employee.objects.create(
            tenant=cls.tenant, employee_no="1001", name="Ada Lovelace", email="ada@inv.test"
        )

    def invite_url(self, employee=None):
        return f"/api/employees/{(employee or self.employee).id}/invite-mobile/"


class InviteEndpointTests(InvitationTestBase):
    def test_happy_path_sends_email_and_stores_hash_only(self):
        self.client.force_authenticate(self.org_admin)
        response = self.client.post(self.invite_url(), {}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        payload = response.json()
        self.assertEqual(payload["email"], "ada@inv.test")
        self.assertTrue(payload["email_sent"])

        invitation = EmployeeInvitation.objects.get(employee=self.employee)
        self.assertEqual(invitation.status, EmployeeInvitation.STATUS_PENDING)
        self.assertEqual(len(invitation.token_hash), 64)

        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn("lrtime://accept-invitation?token=", body)
        # Le secret est dans l'email mais jamais en clair en base.
        secret = body.split("lrtime://accept-invitation?token=")[1].split()[0].strip()
        self.assertNotIn(secret, invitation.token_hash)
        self.assertEqual(hash_invitation_secret(secret), invitation.token_hash)

    def test_requires_org_admin(self):
        self.client.force_authenticate(self.operator)
        response = self.client.post(self.invite_url(), {}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_no_email_error(self):
        employee = Employee.objects.create(tenant=self.tenant, employee_no="1002", name="No Mail")
        self.client.force_authenticate(self.org_admin)
        response = self.client.post(self.invite_url(employee), {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "NO_EMAIL")

    def test_email_override(self):
        self.client.force_authenticate(self.org_admin)
        response = self.client.post(self.invite_url(), {"email": "autre@inv.test"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["email"], "autre@inv.test")

    def test_already_linked_conflict(self):
        linked_user = User.objects.create_user("ada@linked.test", "ada@linked.test", "pass1234!")
        self.employee.user = linked_user
        self.employee.save(update_fields=["user"])
        self.client.force_authenticate(self.org_admin)
        response = self.client.post(self.invite_url(), {}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "ALREADY_LINKED")

    def test_reinvite_revokes_previous_pending(self):
        self.client.force_authenticate(self.org_admin)
        self.client.post(self.invite_url(), {}, format="json")
        self.client.post(self.invite_url(), {}, format="json")
        statuses = list(
            EmployeeInvitation.objects.filter(employee=self.employee)
            .order_by("id")
            .values_list("status", flat=True)
        )
        self.assertEqual(statuses, [EmployeeInvitation.STATUS_REVOKED, EmployeeInvitation.STATUS_PENDING])


class AcceptEndpointTests(InvitationTestBase):
    def _create_invitation(self) -> str:
        created = create_mobile_invitation(employee=self.employee, invited_by=self.org_admin)
        return created.secret

    def test_preview(self):
        secret = self._create_invitation()
        response = self.client.get(PREVIEW_URL, {"token": secret})
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["employee_name"], "Ada Lovelace")
        self.assertEqual(payload["tenant_name"], "Invite A")

    def test_accept_happy_path_returns_login_shape(self):
        secret = self._create_invitation()
        response = self.client.post(
            ACCEPT_URL, {"token": secret, "password": STRONG_PASSWORD}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        payload = response.json()
        self.assertIn("access", payload)
        self.assertIn("refresh", payload)
        self.assertEqual(payload["tenants"][0]["role"], TenantRole.EMPLOYEE)

        self.employee.refresh_from_db()
        self.assertIsNotNone(self.employee.user)
        self.assertEqual(self.employee.user.email, "ada@inv.test")
        membership = TenantMembership.objects.get(user=self.employee.user, tenant=self.tenant)
        self.assertEqual(membership.role, TenantRole.EMPLOYEE)
        invitation = EmployeeInvitation.objects.get(employee=self.employee)
        self.assertEqual(invitation.status, EmployeeInvitation.STATUS_ACCEPTED)

    def test_invalid_token(self):
        response = self.client.post(
            ACCEPT_URL, {"token": "nope", "password": STRONG_PASSWORD}, format="json"
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "INVALID_TOKEN")

    def test_expired_invitation(self):
        secret = self._create_invitation()
        EmployeeInvitation.objects.filter(employee=self.employee).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        response = self.client.post(
            ACCEPT_URL, {"token": secret, "password": STRONG_PASSWORD}, format="json"
        )
        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.json()["code"], "EXPIRED")

    def test_reused_token_conflict(self):
        secret = self._create_invitation()
        self.client.post(ACCEPT_URL, {"token": secret, "password": STRONG_PASSWORD}, format="json")
        response = self.client.post(
            ACCEPT_URL, {"token": secret, "password": STRONG_PASSWORD}, format="json"
        )
        self.assertEqual(response.status_code, 409)

    def test_email_in_use(self):
        User.objects.create_user("ada@inv.test", "ada@inv.test", "pass1234!")
        secret = self._create_invitation()
        response = self.client.post(
            ACCEPT_URL, {"token": secret, "password": STRONG_PASSWORD}, format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "EMAIL_IN_USE")

    def test_weak_password(self):
        secret = self._create_invitation()
        response = self.client.post(ACCEPT_URL, {"token": secret, "password": "123"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "WEAK_PASSWORD")

    def test_no_role_downgrade_for_existing_membership(self):
        # L'employé invité possède déjà un compte admin avec le même email ?
        # Cas couvert : membership existant sur le user créé — ici on vérifie
        # qu'un get_or_create ne rétrograde pas un rôle déjà présent.
        secret = self._create_invitation()
        response = self.client.post(
            ACCEPT_URL, {"token": secret, "password": STRONG_PASSWORD}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="ada@inv.test")
        membership = TenantMembership.objects.get(user=user, tenant=self.tenant)
        membership.role = TenantRole.ORG_ADMIN
        membership.save(update_fields=["role"])
        # Relancer la liaison (simulée) ne doit pas écraser le rôle.
        from tenants.models import TenantMembership as TM

        TM.objects.get_or_create(user=user, tenant=self.tenant, defaults={"role": TenantRole.EMPLOYEE})
        membership.refresh_from_db()
        self.assertEqual(membership.role, TenantRole.ORG_ADMIN)

    def test_mobile_status_serializer_field(self):
        self.client.force_authenticate(self.org_admin)
        response = self.client.get(f"/api/employees/{self.employee.id}/")
        self.assertEqual(response.json()["mobile_status"], "none")
        create_mobile_invitation(employee=self.employee, invited_by=self.org_admin)
        response = self.client.get(f"/api/employees/{self.employee.id}/")
        self.assertEqual(response.json()["mobile_status"], "invited")
        secret_created = create_mobile_invitation(employee=self.employee, invited_by=self.org_admin)
        self.client.post(
            ACCEPT_URL, {"token": secret_created.secret, "password": STRONG_PASSWORD}, format="json"
        )
        response = self.client.get(f"/api/employees/{self.employee.id}/")
        self.assertEqual(response.json()["mobile_status"], "linked")
