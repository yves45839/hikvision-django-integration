from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from employees.models import Organization, OrganizationInvitation, OrganizationMembership, OrganizationRole
from tenants.models import (
    EmailVerificationToken,
    OrganizationCustomRole,
    OrganizationCustomRoleAssignment,
    PaymentStatus,
    PasswordResetToken,
    Tenant,
    TenantMembership,
    TenantRole,
)


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
        token = str(
            EmailVerificationToken.objects.filter(user__email__iexact="owner2@acme.test")
            .latest("id")
            .token
        )
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
        token = str(
            EmailVerificationToken.objects.filter(user__email__iexact="owner3@acme.test")
            .latest("id")
            .token
        )
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

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_verification_can_use_otp(self):
        signup = self.client.post(
            "/api/auth/client-signup/",
            {
                "email": "otp-owner@acme.test",
                "password": "StrongPass123",
                "tenant_name": "Acme OTP",
                "domain": "acme.test",
            },
            format="json",
        )
        self.assertEqual(signup.status_code, status.HTTP_201_CREATED)
        otp = (
            EmailVerificationToken.objects.filter(user__email__iexact="otp-owner@acme.test")
            .latest("id")
            .otp_code
        )

        verify = self.client.post(
            "/api/auth/verify-email/",
            {"email": "otp-owner@acme.test", "otp": otp},
            format="json",
        )
        self.assertEqual(verify.status_code, status.HTTP_200_OK)
        self.assertEqual(verify.json()["status"], "verified")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_resend_verification_generates_new_otp(self):
        signup = self.client.post(
            "/api/auth/client-signup/",
            {
                "email": "resend-owner@acme.test",
                "password": "StrongPass123",
                "tenant_name": "Acme Resend",
            },
            format="json",
        )
        self.assertEqual(signup.status_code, status.HTTP_201_CREATED)
        original_otp = (
            EmailVerificationToken.objects.filter(user__email__iexact="resend-owner@acme.test")
            .latest("id")
            .otp_code
        )

        resend = self.client.post(
            "/api/auth/resend-verification/",
            {"email": "resend-owner@acme.test"},
            format="json",
        )
        self.assertEqual(resend.status_code, status.HTTP_200_OK)
        updated_otp = (
            EmailVerificationToken.objects.filter(user__email__iexact="resend-owner@acme.test")
            .latest("id")
            .otp_code
        )
        self.assertNotEqual(updated_otp, original_otp)
        self.assertGreaterEqual(len(mail.outbox), 2)


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
        token = str(
            OrganizationInvitation.objects.filter(
                organization=self.organization,
                email="operator@invite.test",
            )
            .latest("id")
            .token
        )

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


class TenantUserRoleManagementTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Tenant Admin",
            code="tenant-admin",
            domain="tenant.test",
            is_domain_verified=True,
            is_active=True,
        )
        self.organization = Organization.objects.create(
            tenant=self.tenant,
            name="Main Org",
            code="MAIN",
        )
        self.owner = User.objects.create_user(
            username="owner-tenant",
            email="owner@tenant.test",
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

    def test_org_admin_can_create_role_create_user_and_assign_role(self):
        create_role = self.client.post(
            f"/api/auth/organizations/{self.organization.id}/roles/",
            {
                "name": "superviseur-nuit",
                "description": "Supervision de nuit",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(create_role.status_code, status.HTTP_201_CREATED)
        role_id = create_role.json()["id"]

        create_user = self.client.post(
            f"/api/auth/organizations/{self.organization.id}/users/",
            {
                "email": "agent1@tenant.test",
                "password": "AgentPass123",
                "first_name": "Agent",
                "last_name": "Un",
                "tenant_role": TenantRole.OPERATOR,
                "organization_role": OrganizationRole.OPERATOR,
                "custom_role_ids": [role_id],
            },
            format="json",
        )
        self.assertEqual(create_user.status_code, status.HTTP_201_CREATED)
        created_user_id = create_user.json()["user"]["id"]

        self.assertTrue(
            TenantMembership.objects.filter(
                user_id=created_user_id,
                tenant=self.tenant,
                role=TenantRole.OPERATOR,
            ).exists()
        )
        self.assertTrue(
            OrganizationMembership.objects.filter(
                user_id=created_user_id,
                organization=self.organization,
                role=OrganizationRole.OPERATOR,
            ).exists()
        )
        self.assertTrue(
            OrganizationCustomRoleAssignment.objects.filter(
                organization=self.organization,
                role_id=role_id,
                user_id=created_user_id,
            ).exists()
        )

        list_users = self.client.get(f"/api/auth/organizations/{self.organization.id}/users/")
        self.assertEqual(list_users.status_code, status.HTTP_200_OK)
        payload = list_users.json()
        target = next(row for row in payload["results"] if row["id"] == created_user_id)
        self.assertEqual(target["organization_role"], OrganizationRole.OPERATOR)
        self.assertEqual(target["tenant_role"], TenantRole.OPERATOR)
        self.assertEqual([row["id"] for row in target["custom_roles"]], [role_id])

    def test_viewer_cannot_manage_org_users_or_roles(self):
        viewer = User.objects.create_user(
            username="viewer-role",
            email="viewer-role@tenant.test",
            password="StrongPass123",
            is_active=True,
        )
        TenantMembership.objects.create(
            user=viewer,
            tenant=self.tenant,
            role=TenantRole.VIEWER,
            is_primary=True,
        )
        OrganizationMembership.objects.create(
            user=viewer,
            organization=self.organization,
            role=OrganizationRole.VIEWER,
        )

        self.client.force_authenticate(viewer)
        response = self.client.post(
            f"/api/auth/organizations/{self.organization.id}/roles/",
            {"name": "interdit"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_org_admin_cannot_grant_tenant_admin_role(self):
        org_admin = User.objects.create_user(
            username="org-admin-limited",
            email="org-admin-limited@tenant.test",
            password="StrongPass123",
            is_active=True,
        )
        TenantMembership.objects.create(
            user=org_admin,
            tenant=self.tenant,
            role=TenantRole.ORG_ADMIN,
            is_primary=True,
        )
        OrganizationMembership.objects.create(
            user=org_admin,
            organization=self.organization,
            role=OrganizationRole.ORG_ADMIN,
        )

        self.client.force_authenticate(org_admin)
        response = self.client.post(
            f"/api/auth/organizations/{self.organization.id}/users/",
            {
                "email": "new-admin@tenant.test",
                "password": "StrongPass123",
                "tenant_role": TenantRole.TENANT_ADMIN,
                "organization_role": OrganizationRole.ORG_ADMIN,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AuthProfileTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="profile-user",
            email="profile@tenant.test",
            password="StrongPass123",
            is_active=True,
            first_name="Old",
            last_name="Name",
        )
        self.tenant = Tenant.objects.create(
            name="Tenant Profile",
            code="tenant-profile",
            domain="tenant.test",
            is_domain_verified=True,
            is_active=True,
        )
        TenantMembership.objects.create(
            user=self.user,
            tenant=self.tenant,
            role=TenantRole.VIEWER,
            is_primary=True,
        )

    def test_login_profile_change_password_and_logout(self):
        login = self.client.post(
            "/api/auth/login/",
            {"email": "profile@tenant.test", "password": "StrongPass123"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        access = login.json()["access"]
        refresh = login.json()["refresh"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        profile = self.client.get("/api/auth/profile/")
        self.assertEqual(profile.status_code, status.HTTP_200_OK)
        self.assertEqual(profile.json()["email"], "profile@tenant.test")

        patch_profile = self.client.patch(
            "/api/auth/profile/",
            {"first_name": "New", "last_name": "Profile"},
            format="json",
        )
        self.assertEqual(patch_profile.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_profile.json()["first_name"], "New")

        change_password = self.client.post(
            "/api/auth/change-password/",
            {"old_password": "StrongPass123", "new_password": "BrandNewPass123"},
            format="json",
        )
        self.assertEqual(change_password.status_code, status.HTTP_200_OK)

        logout = self.client.post("/api/auth/logout/", {"refresh": refresh}, format="json")
        self.assertEqual(logout.status_code, status.HTTP_200_OK)

        old_login = self.client.post(
            "/api/auth/login/",
            {"email": "profile@tenant.test", "password": "StrongPass123"},
            format="json",
        )
        self.assertEqual(old_login.status_code, status.HTTP_401_UNAUTHORIZED)

        new_login = self.client.post(
            "/api/auth/login/",
            {"email": "profile@tenant.test", "password": "BrandNewPass123"},
            format="json",
        )
        self.assertEqual(new_login.status_code, status.HTTP_200_OK)

    def test_assign_custom_role_endpoint(self):
        manager = User.objects.create_user(
            username="manager-profile",
            email="manager@tenant.test",
            password="StrongPass123",
            is_active=True,
        )
        TenantMembership.objects.create(user=manager, tenant=self.tenant, role=TenantRole.ORG_ADMIN)
        organization = Organization.objects.create(tenant=self.tenant, name="Profile Org", code="PROF")
        OrganizationMembership.objects.create(user=manager, organization=organization, role=OrganizationRole.ORG_ADMIN)

        member = User.objects.create_user(
            username="member-profile",
            email="member@tenant.test",
            password="StrongPass123",
            is_active=True,
        )
        TenantMembership.objects.create(user=member, tenant=self.tenant, role=TenantRole.VIEWER)
        OrganizationMembership.objects.create(user=member, organization=organization, role=OrganizationRole.VIEWER)

        role = OrganizationCustomRole.objects.create(
            tenant=self.tenant,
            organization=organization,
            name="controller",
            created_by=manager,
        )

        self.client.force_authenticate(manager)
        response = self.client.post(
            f"/api/auth/organizations/{organization.id}/roles/{role.id}/assign/",
            {"user_id": member.id, "assigned": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            OrganizationCustomRoleAssignment.objects.filter(
                organization=organization,
                role=role,
                user=member,
            ).exists()
        )


class AuthPasswordResetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reset-user",
            email="reset@tenant.test",
            password="StrongPass123",
            is_active=True,
        )
        self.tenant = Tenant.objects.create(
            name="Tenant Reset",
            code="tenant-reset",
            domain="tenant.test",
            is_domain_verified=True,
            is_active=True,
        )
        TenantMembership.objects.create(
            user=self.user,
            tenant=self.tenant,
            role=TenantRole.VIEWER,
            is_primary=True,
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_with_otp(self):
        request_reset = self.client.post(
            "/api/auth/password-reset/request/",
            {"email": "reset@tenant.test"},
            format="json",
        )
        self.assertEqual(request_reset.status_code, status.HTTP_200_OK)
        otp = PasswordResetToken.objects.filter(user=self.user).latest("id").otp_code

        confirm = self.client.post(
            "/api/auth/password-reset/confirm/",
            {
                "email": "reset@tenant.test",
                "otp": otp,
                "new_password": "BrandNewPass123",
            },
            format="json",
        )
        self.assertEqual(confirm.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm.json()["status"], "password_reset")

        login = self.client.post(
            "/api/auth/login/",
            {"email": "reset@tenant.test", "password": "BrandNewPass123"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_with_token(self):
        request_reset = self.client.post(
            "/api/auth/password-reset/request/",
            {"identifier": "reset-user"},
            format="json",
        )
        self.assertEqual(request_reset.status_code, status.HTTP_200_OK)
        token = str(PasswordResetToken.objects.filter(user=self.user).latest("id").token)

        confirm = self.client.post(
            "/api/auth/password-reset/confirm/",
            {
                "token": token,
                "new_password": "AnotherPass123",
            },
            format="json",
        )
        self.assertEqual(confirm.status_code, status.HTTP_200_OK)

        login = self.client.post(
            "/api/auth/login/",
            {"username": "reset-user", "password": "AnotherPass123"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
