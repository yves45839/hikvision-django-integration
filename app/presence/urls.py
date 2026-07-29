from django.urls import path

from presence.mobile_views import (
    mobile_history_api,
    mobile_me_api,
    mobile_punch_api,
    mobile_push_token_api,
)
from presence.views import (
    mobile_invitation_accept_api,
    mobile_invitation_preview_api,
    punch_notification_settings_api,
)

urlpatterns = [
    path("mobile/me/", mobile_me_api, name="mobile-me"),
    path("mobile/punch/", mobile_punch_api, name="mobile-punch"),
    path("mobile/history/", mobile_history_api, name="mobile-history"),
    path("mobile/push-token/", mobile_push_token_api, name="mobile-push-token"),
    path(
        "punch-notification-settings/",
        punch_notification_settings_api,
        name="punch-notification-settings",
    ),
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
