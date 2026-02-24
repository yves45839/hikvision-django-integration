from rest_framework import serializers
from .models import AttendanceEvent

class AttendanceEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceEvent
        fields = ['id', 'tenant', 'device', 'user_id', 'timestamp', 'event_type', 'created_at']
