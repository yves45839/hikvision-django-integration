from django.urls import path

from tenants.auth_views import (
    accept_organization_invitation_api,
    assign_custom_role_api,
    change_password_api,
    confirm_password_reset_api,
    client_signup_api,
    request_password_reset_api,
    create_organization_invitation_api,
    login_api,
    logout_api,
    my_organizations_api,
    organization_custom_roles_api,
    organization_users_api,
    payment_callback_api,
    profile_api,
    resend_email_verification_api,
    verify_email_api,
)
from tenants.gdpr_views import UserDataExportView, UserDeleteView
from tenants.dpa_views import DPADownloadView

urlpatterns = [
    path("auth/client-signup/", client_signup_api, name="auth-client-signup"),
    path("auth/login/", login_api, name="auth-login"),
    path("auth/logout/", logout_api, name="auth-logout"),
    path("auth/profile/", profile_api, name="auth-profile"),
    path("auth/change-password/", change_password_api, name="auth-change-password"),
    path("auth/verify-email/", verify_email_api, name="auth-verify-email"),
    path("auth/resend-verification/", resend_email_verification_api, name="auth-resend-verification"),
    path("auth/password-reset/request/", request_password_reset_api, name="auth-password-reset-request"),
    path("auth/password-reset/confirm/", confirm_password_reset_api, name="auth-password-reset-confirm"),
    path("auth/payment-callback/", payment_callback_api, name="auth-payment-callback"),
    path("auth/me/organizations/", my_organizations_api, name="auth-my-organizations"),
    path(
        "auth/organizations/<int:organization_id>/invite/",
        create_organization_invitation_api,
        name="auth-org-invite",
    ),
    path(
        "auth/organizations/<int:organization_id>/users/",
        organization_users_api,
        name="auth-org-users",
    ),
    path(
        "auth/organizations/<int:organization_id>/roles/",
        organization_custom_roles_api,
        name="auth-org-roles",
    ),
    path(
        "auth/organizations/<int:organization_id>/roles/<int:role_id>/assign/",
        assign_custom_role_api,
        name="auth-org-role-assign",
    ),
    path("auth/invitations/accept/", accept_organization_invitation_api, name="auth-invitations-accept"),
    # RGPD endpoints
    path("auth/me/export/", UserDataExportView.as_view(), name="auth-me-export"),
    path("auth/me/", UserDeleteView.as_view(), name="auth-me-delete"),
    path("auth/dpa/", DPADownloadView.as_view(), name="auth-dpa"),
]
