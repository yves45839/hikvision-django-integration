from rest_framework import serializers
from .models import Device


class DeviceSerializer(serializers.ModelSerializer):
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    ip_address = serializers.CharField(read_only=True)
    serial_number = serializers.CharField(required=True, min_length=1, max_length=31)

    class Meta:
        model = Device
        fields = [
            'id',
            'owner',
            'tenant',
            'ip_address',
            'port',
            'serial_number',
            'dev_index',
            'device_id',
            'name',
            'model',
            'protocol',
            'status',
            'created_at',
        ]
        read_only_fields = ['created_at', 'protocol', 'status', 'device_id', 'model']

    def create(self, validated_data):
        validated_data['protocol'] = 'ISUP'
        return super().create(validated_data)


class DeviceOnboardSerializer(serializers.Serializer):
    tenant_code = serializers.CharField(max_length=50)
    sn = serializers.CharField(max_length=31)
    ehome_key = serializers.CharField(max_length=32, write_only=True)
    dev_name = serializers.CharField(max_length=255)
    dev_type = serializers.CharField(max_length=64, default='AccessControl')

    def validate_dev_type(self, value):
        if value != 'AccessControl':
            raise serializers.ValidationError('dev_type doit être AccessControl.')
        return value
