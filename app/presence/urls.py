from django.urls import path

from presence.views import mobile_invitation_accept_api, mobile_invitation_preview_api

urlpatterns = [
    path(
        "auth/employee-invitations/preview/",
        mobile_invitation_preview_api,
        name="mobile-invitation-preview",
    ),
    path(
        "auth/employee-invitations/accept/",
        mobile_invitation_accept_api,
        name="mobile-invitation-accept",
    ),
]
