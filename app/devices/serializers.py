from rest_framework import serializers

from .models import Device, DeviceOnboardingJob, DeviceOrganizationBinding


class DeviceSerializer(serializers.ModelSerializer):
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    ip_address = serializers.CharField(read_only=True)
    serial_number = serializers.CharField(required=True, min_length=1, max_length=31)
    device_password = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = Device
        fields = [
            "id",
            "owner",
            "tenant",
            "ip_address",
            "port",
            "serial_number",
            "dev_index",
            "device_id",
            "name",
            "model",
            "protocol",
            "status",
            "device_username",
            "device_password",
            "created_at",
        ]
        read_only_fields = ["created_at", "protocol", "status", "device_id", "model"]

    def create(self, validated_data):
        validated_data["protocol"] = "ISUP"
        return super().create(validated_data)


class DeviceOnboardSerializer(serializers.Serializer):
    tenant_code = serializers.CharField(max_length=50)
    sn = serializers.CharField(max_length=31)
    ehome_key = serializers.CharField(max_length=32, write_only=True)
    dev_name = serializers.CharField(max_length=255)
    dev_type = serializers.CharField(max_length=64, default="AccessControl")
    device_username = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    device_password = serializers.CharField(max_length=255, required=False, allow_blank=True, default="", write_only=True)

    def validate_dev_type(self, value):
        if value != "AccessControl":
            raise serializers.ValidationError("dev_type must be AccessControl.")
        return value


class DeviceOrganizationBindingSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceOrganizationBinding
        fields = ["id", "organization", "is_primary", "assigned_by", "created_at"]
        read_only_fields = ["id", "assigned_by", "created_at"]


class DeviceOnboardingJobCreateSerializer(serializers.Serializer):
    tenant_code = serializers.CharField(max_length=50)
    organization_id = serializers.IntegerField()
    sn = serializers.CharField(max_length=31)
    ehome_key = serializers.CharField(max_length=32, write_only=True)
    dev_name = serializers.CharField(max_length=255)
    dev_type = serializers.CharField(max_length=64, default="AccessControl")
    device_username = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    device_password = serializers.CharField(max_length=255, required=False, allow_blank=True, default="", write_only=True)

    def validate_dev_type(self, value):
        if value != "AccessControl":
            raise serializers.ValidationError("dev_type must be AccessControl.")
        return value


class DeviceOnboardingJobSerializer(serializers.ModelSerializer):
    device = DeviceSerializer(read_only=True)

    class Meta:
        model = DeviceOnboardingJob
        fields = [
            "id",
            "tenant",
            "organization",
            "requested_by",
            "device",
            "status",
            "review_reason",
            "error_message",
            "gateway_status",
            "request_payload",
            "sn",
            "dev_name",
            "dev_type",
            "device_username",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
        ]
        read_only_fields = fields
