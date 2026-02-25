from rest_framework import serializers
from .models import Device


class DeviceSerializer(serializers.ModelSerializer):
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    ip_address = serializers.CharField(read_only=True)
    serial_number = serializers.CharField(required=True, min_length=9, max_length=9)

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
            'model',
            'protocol',
            'status',
            'created_at',
        ]
        read_only_fields = ['created_at', 'protocol', 'status', 'device_id', 'model']

    def validate_serial_number(self, value):
        if len(value) != 9:
            raise serializers.ValidationError('Le numéro de série doit contenir exactement 9 caractères.')
        return value

    def create(self, validated_data):
        validated_data['protocol'] = 'ISUP'
        return super().create(validated_data)
