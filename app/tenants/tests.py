from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from employees.models import Organization, OrganizationInvitation, OrganizationMembership, OrganizationRole
from tenants.models import EmailVerificationToken, PaymentStatus, Tenant, TenantMembership, TenantRole


User = get_user_model()


class TenantAutomationFlowTests(APITestCase):
    def test_client_signup_creates_tenant_default_org_and_memberships(self):
        response = self.client.post(
            "/api/auth/client-signup/",
            {
                "email": "owner@acme.test",
                "password": "StrongPass123",
                "tenant_name": "Acme",
                "organization_name": "Acme HQ",
                "require_payment": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payload = response.json()
        tenant = Tenant.objects.get(code=payload["tenant"]["code"])
        user = User.objects.get(id=payload["user"]["id"])
        org = Organization.objects.get(id=payload["default_organization"]["id"])

        self.assertFalse(tenant.is_active)
        self.assertEqual(org.tenant_id, tenant.id)
        self.assertTrue(
            TenantMembership.objects.filter(
                user=user,
                tenant=tenant,
                role=TenantRole.TENANT_ADMIN,
            ).exists()
        )
        self.assertTrue(
            OrganizationMembership.objects.filter(
                user=user,
                organization=org,
                role=OrganizationRole.ORG_ADMIN,
            ).exists()
        )
        self.assertTrue(
            EmailVerificationToken.objects.filter(
                token=payload["email_verification_token"],
                tenant=tenant,
                user=user,
                is_used=False,
            ).exists()
        )

    def test_email_verification_auto_activates_when_payment_not_required(self):
        signup = self.client.post(
            "/api/auth/client-signup/",
            {
                "email": "owner2@acme.test",
                "password": "StrongPass123",
                "tenant_name": "Acme2",
                "domain": "acme.test",
                "require_payment": False,
            },
            format="json",
        )
        token = signup.json()["email_verification_token"]
        tenant_code = signup.json()["tenant"]["code"]

        verify = self.client.post("/api/auth/verify-email/", {"token": token}, format="json")
        self.assertEqual(verify.status_code, status.HTTP_200_OK)
        self.assertTrue(verify.json()["tenant"]["is_active"])

        tenant = Tenant.objects.get(code=tenant_code)
        self.assertTrue(tenant.is_active)
        self.assertEqual(tenant.payment_status, PaymentStatus.NOT_REQUIRED)

    def test_payment_callback_activates_tenant_after_email_verification(self):
        signup = self.client.post(
            "/api/auth/client-signup/",
            {
                "email": "owner3@acme.test",
                "password": "StrongPass123",
                "tenant_name": "Acme3",
                "domain": "acme.test",
                "require_payment": True,
            },
            format="json",
        )
        token = signup.json()["email_verification_token"]
        tenant_code = signup.json()["tenant"]["code"]

        verify = self.client.post("/api/auth/verify-email/", {"token": token}, format="json")
        self.assertEqual(verify.status_code, status.HTTP_200_OK)
        self.assertFalse(verify.json()["tenant"]["is_active"])

        callback = self.client.post(
            "/api/auth/payment-callback/",
            {
                "tenant_code": tenant_code,
                "payment_status": PaymentStatus.PAID,
            },
            format="json",
        )
        self.assertEqual(callback.status_code, status.HTTP_200_OK)
        self.assertTrue(callback.json()["is_active"])
        self.assertEqual(callback.json()["payment_status"], PaymentStatus.PAID)

    @override_settings(PAYMENT_WEBHOOK_TOKEN="secret-payment")
    def test_payment_callback_rejects_invalid_token(self):
        tenant = Tenant.objects.create(
            name="Secured",
            code="secured-tenant",
            domain="secured.test",
            is_domain_verified=True,
            is_active=False,
            payment_status=PaymentStatus.PENDING,
        )
        response = self.client.post(
            "/api/auth/payment-callback/",
            {"tenant_code": tenant.code, "payment_status": PaymentStatus.PAID},
            format="json",
            HTTP_X_PAYMENT_TOKEN="wrong-token",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class InvitationFlowTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Tenant Invite",
            code="tenant-invite",
            domain="invite.test",
            is_domain_verified=True,
            is_active=True,
        )
        self.organization = Organization.objects.create(
            tenant=self.tenant,
            name="Operations",
            code="OPS",
        )
        self.owner = User.objects.create_user(
            username="owner-invite",
            email="owner@invite.test",
            password="StrongPass123",
            is_active=True,
        )
        TenantMembership.objects.create(
            user=self.owner,
            tenant=self.tenant,
            role=TenantRole.TENANT_ADMIN,
            is_primary=True,
        )
        OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.organization,
            role=OrganizationRole.ORG_ADMIN,
        )
        self.client.force_authenticate(self.owner)

    def test_magic_invite_and_accept_assigns_org_membership(self):
        invite = self.client.post(
            f"/api/auth/organizations/{self.organization.id}/invite/",
            {"email": "operator@invite.test", "role": OrganizationRole.OPERATOR},
            format="json",
        )
        self.assertEqual(invite.status_code, status.HTTP_201_CREATED)
        token = invite.json()["magic_link_token"]

        self.client.force_authenticate(user=None)
        accept = self.client.post(
            "/api/auth/invitations/accept/",
            {
                "token": token,
                "username": "operator-invite",
                "password": "OperatorPass123",
            },
            format="json",
        )
        self.assertEqual(accept.status_code, status.HTTP_200_OK)

        invited_user = User.objects.get(username="operator-invite")
        self.assertTrue(
            OrganizationMembership.objects.filter(
                user=invited_user,
                organization=self.organization,
                role=OrganizationRole.OPERATOR,
            ).exists()
        )
        self.assertTrue(
            TenantMembership.objects.filter(
                user=invited_user,
                tenant=self.tenant,
                role=TenantRole.OPERATOR,
            ).exists()
        )
        invitation = OrganizationInvitation.objects.get(token=token)
        self.assertEqual(invitation.status, OrganizationInvitation.STATUS_ACCEPTED)

    def test_my_organizations_returns_only_user_scope(self):
        extra_org = Organization.objects.create(
            tenant=self.tenant,
            name="Secret",
            code="SECRET",
        )
        outsider = User.objects.create_user(
            username="viewer-invite",
            email="viewer@invite.test",
            password="StrongPass123",
            is_active=True,
        )
        TenantMembership.objects.create(
            user=outsider,
            tenant=self.tenant,
            role=TenantRole.VIEWER,
            is_primary=True,
        )
        OrganizationMembership.objects.create(
            user=outsider,
            organization=self.organization,
            role=OrganizationRole.VIEWER,
        )

        self.client.force_authenticate(outsider)
        response = self.client.get("/api/auth/me/organizations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        org_ids = {item["id"] for item in payload["results"][0]["organizations"]}
        self.assertIn(self.organization.id, org_ids)
        self.assertNotIn(extra_org.id, org_ids)

    def test_organizations_api_is_scoped_by_membership(self):
        extra_org = Organization.objects.create(
            tenant=self.tenant,
            name="Finance",
            code="FIN",
        )
        user = User.objects.create_user(
            username="org-scoped-user",
            email="scoped@invite.test",
            password="StrongPass123",
            is_active=True,
        )
        TenantMembership.objects.create(
            user=user,
            tenant=self.tenant,
            role=TenantRole.VIEWER,
            is_primary=True,
        )
        OrganizationMembership.objects.create(
            user=user,
            organization=self.organization,
            role=OrganizationRole.VIEWER,
        )

        self.client.force_authenticate(user)
        response = self.client.get("/api/organizations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.json()}
        self.assertIn(self.organization.id, ids)
        self.assertNotIn(extra_org.id, ids)
