from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer


class SafeTokenRefreshSerializer(TokenRefreshSerializer):
    """
    Convert orphaned refresh tokens (user deleted/missing) into auth errors
    instead of uncaught DoesNotExist exceptions.
    """

    def validate(self, attrs):
        try:
            return super().validate(attrs)
        except get_user_model().DoesNotExist as exc:
            raise AuthenticationFailed(
                self.error_messages["no_active_account"],
                "no_active_account",
            ) from exc
