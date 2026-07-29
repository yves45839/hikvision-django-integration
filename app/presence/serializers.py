from rest_framework import serializers

from presence.models import Site


class SiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Site
        fields = [
            "id",
            "tenant",
            "name",
            "address",
            "latitude",
            "longitude",
            "radius_m",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_latitude(self, value):
        if not (-90 <= value <= 90):
            raise serializers.ValidationError("La latitude doit être comprise entre -90 et 90.")
        return value

    def validate_longitude(self, value):
        if not (-180 <= value <= 180):
            raise serializers.ValidationError("La longitude doit être comprise entre -180 et 180.")
        return value

    def validate_radius_m(self, value):
        if not (30 <= value <= 2000):
            raise serializers.ValidationError("Le rayon doit être compris entre 30 et 2000 mètres.")
        return value
