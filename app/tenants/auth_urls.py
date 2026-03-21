from django.urls import path

from tenants.auth_views import (
    accept_organization_invitation_api,
    client_signup_api,
    create_organization_invitation_api,
    my_organizations_api,
    payment_callback_api,
    verify_email_api,
)


urlpatterns = [
    path("auth/client-signup/", client_signup_api, name="auth-client-signup"),
    path("auth/verify-email/", verify_email_api, name="auth-verify-email"),
    path("auth/payment-callback/", payment_callback_api, name="auth-payment-callback"),
    path(
        "auth/organizations/<int:organization_id>/invite/",
        create_organization_invitation_api,
        name="auth-org-invite",
    ),
    path("auth/invitations/accept/", accept_organization_invitation_api, name="auth-invite-accept"),
    path("auth/me/organizations/", my_organizations_api, name="auth-me-organizations"),
]
