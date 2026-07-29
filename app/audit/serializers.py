from rest_framework import serializers

from audit.models import AuditEvent


class AuditActorSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)


class AuditEventSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "actor",
            "action",
            "target_model",
            "target_id",
            "ip_address",
            "tenant_code",
            "extra",
            "created_at",
        ]

    def get_actor(self, obj):
        if obj.actor_id is None:
            return None
        return {
            "id": obj.actor_id,
            "username": obj.actor.get_username(),
            "email": getattr(obj.actor, "email", "") or "",
        }
