from django.contrib.auth import get_user_model
from rest_framework import serializers

from employees.models import OrganizationRole
from tenants.models import OrganizationCustomRole, Tenant, TenantRole


User = get_user_model()


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = [
            "id",
            "name",
            "code",
            "domain",
            "is_domain_verified",
            "is_active",
            "device_quota",
            "payment_status",
            "requires_manual_review",
            "created_at",
        ]


class AuthUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
        ]
        read_only_fields = ["id", "is_active"]


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)


class OrganizationUserCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    username = serializers.CharField(required=False, allow_blank=True, max_length=150)
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    tenant_role = serializers.ChoiceField(
        choices=TenantRole.choices,
        default=TenantRole.VIEWER,
        required=False,
    )
    organization_role = serializers.ChoiceField(
        choices=OrganizationRole.choices,
        default=OrganizationRole.VIEWER,
        required=False,
    )
    custom_role_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
    )

    def validate_email(self, value):
        email = str(value or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email


class OrganizationCustomRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationCustomRole
        fields = [
            "id",
            "tenant",
            "organization",
            "name",
            "description",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant", "organization", "created_by", "created_at", "updated_at"]
