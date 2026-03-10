from rest_framework import serializers

from devices.models import Device
from employees.models import (
    Department,
    Employee,
    EmployeeAttribute,
    EmployeeCard,
    EmployeeFace,
    EmployeeFingerprint,
    Organization,
    Planning,
)


class EmployeeAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeAttribute
        fields = ["id", "name", "value", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class EmployeeCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeCard
        fields = ["id", "card_no", "card_type", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class EmployeeFingerprintSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeFingerprint
        fields = ["id", "finger_index", "template", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class EmployeeFaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeFace
        fields = ["id", "face_data", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class EmployeeSerializer(serializers.ModelSerializer):
    attributes = EmployeeAttributeSerializer(many=True, required=False)
    devices = serializers.PrimaryKeyRelatedField(many=True, queryset=Device.objects.all(), required=False)
    cards = EmployeeCardSerializer(many=True, required=False)
    fingerprints = EmployeeFingerprintSerializer(many=True, required=False)
    face = EmployeeFaceSerializer(required=False, allow_null=True)
    full_name = serializers.CharField(read_only=True)
    effective_planning = serializers.SerializerMethodField(read_only=True)
    require_credential = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Employee
        fields = [
            "id",
            "tenant",
            "devices",
            "department",
            "employee_no",
            "name",
            "first_name",
            "last_name",
            "full_name",
            "effective_planning",
            "gender",
            "email",
            "phone",
            "valid_from",
            "valid_to",
            "remark",
            "cards",
            "fingerprints",
            "face",
            "access_group",
            "pin_code",
            "is_super_user",
            "extended_door_open_time",
            "is_blocklisted",
            "is_visitor",
            "is_device_operator",
            "custom_profile",
            "only_authenticate",
            "date_of_birth",
            "identity_type",
            "identity_no",
            "position",
            "hire_date",
            "address",
            "require_credential",
            "is_active",
            "attributes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "full_name"]
        extra_kwargs = {
            "name": {"allow_blank": False},
        }

    def get_effective_planning(self, obj):
        planning = obj.effective_planning
        if planning is None:
            return None
        return {
            "id": planning.id,
            "tenant": planning.tenant_id,
            "name": planning.name,
            "code": planning.code,
        }

    def validate(self, attrs):
        tenant = attrs.get("tenant") or getattr(self.instance, "tenant", None)
        devices = attrs.get("devices")
        department = attrs.get("department") or getattr(self.instance, "department", None)
        name = attrs.get("name")
        require_credential = bool(attrs.get("require_credential"))
        cards = attrs.get("cards")
        fingerprints = attrs.get("fingerprints")
        face = attrs.get("face")

        if tenant and devices:
            invalid_device_ids = [device.id for device in devices if device.tenant_id != tenant.id]
            if invalid_device_ids:
                raise serializers.ValidationError(
                    {"devices": f"Devices hors tenant: {invalid_device_ids}"}
                )

        if tenant and department and department.tenant_id != tenant.id:
            raise serializers.ValidationError({"department": "Le departement doit appartenir au meme tenant."})

        effective_name = name if name is not None else getattr(self.instance, "name", "")
        if not str(effective_name or "").strip():
            raise serializers.ValidationError({"name": "Ce champ est obligatoire."})

        if fingerprints is not None:
            if len(fingerprints) > 10:
                raise serializers.ValidationError({"fingerprints": "Maximum 10 empreintes."})
            slots = [fp["finger_index"] for fp in fingerprints]
            if len(slots) != len(set(slots)):
                raise serializers.ValidationError({"fingerprints": "Chaque finger_index doit etre unique."})

        if require_credential:
            existing_cards = self.instance.cards.exists() if self.instance is not None else False
            existing_fingerprints = self.instance.fingerprints.exists() if self.instance is not None else False
            if self.instance is not None:
                try:
                    existing_face = self.instance.face is not None
                except EmployeeFace.DoesNotExist:
                    existing_face = False
            else:
                existing_face = False

            has_cards = bool(cards) if cards is not None else existing_cards
            has_fingerprints = bool(fingerprints) if fingerprints is not None else existing_fingerprints
            has_face = (face is not None and face != {}) if "face" in attrs else existing_face
            if not any([has_cards, has_fingerprints, has_face]):
                raise serializers.ValidationError(
                    {"non_field_errors": "Au moins un credential (card/fingerprint/face) est requis."}
                )

        return attrs

    def create(self, validated_data):
        attributes_data = validated_data.pop("attributes", [])
        devices = validated_data.pop("devices", [])
        cards_data = validated_data.pop("cards", [])
        fingerprints_data = validated_data.pop("fingerprints", [])
        face_data = validated_data.pop("face", None)
        validated_data.pop("require_credential", None)

        employee = Employee.objects.create(**validated_data)
        if devices:
            employee.devices.set(devices)
        for item in attributes_data:
            EmployeeAttribute.objects.create(employee=employee, **item)
        for card in cards_data:
            EmployeeCard.objects.create(employee=employee, **card)
        for fingerprint in fingerprints_data:
            EmployeeFingerprint.objects.create(employee=employee, **fingerprint)
        if face_data:
            EmployeeFace.objects.create(employee=employee, **face_data)
        return employee

    def update(self, instance, validated_data):
        attributes_data = validated_data.pop("attributes", None)
        devices = validated_data.pop("devices", None)
        cards_data = validated_data.pop("cards", None)
        fingerprints_data = validated_data.pop("fingerprints", None)
        face_data = validated_data.pop("face", serializers.empty)
        validated_data.pop("require_credential", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if devices is not None:
            instance.devices.set(devices)

        if attributes_data is not None:
            existing_by_name = {attr.name: attr for attr in instance.attributes.all()}
            sent_names = set()
            for payload in attributes_data:
                name = payload["name"]
                sent_names.add(name)
                current = existing_by_name.get(name)
                if current is None:
                    EmployeeAttribute.objects.create(employee=instance, **payload)
                else:
                    current.value = payload["value"]
                    current.save(update_fields=["value", "updated_at"])
            for name, current in existing_by_name.items():
                if name not in sent_names:
                    current.delete()

        if cards_data is not None:
            instance.cards.all().delete()
            for payload in cards_data:
                EmployeeCard.objects.create(employee=instance, **payload)

        if fingerprints_data is not None:
            instance.fingerprints.all().delete()
            for payload in fingerprints_data:
                EmployeeFingerprint.objects.create(employee=instance, **payload)

        if face_data is not serializers.empty:
            if face_data is None:
                if hasattr(instance, "face"):
                    instance.face.delete()
            else:
                EmployeeFace.objects.update_or_create(employee=instance, defaults=face_data)

        return instance


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "tenant", "name", "code", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class PlanningSerializer(serializers.ModelSerializer):
    class Meta:
        model = Planning
        fields = ["id", "tenant", "name", "code", "description", "timezone", "metadata", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class DepartmentSerializer(serializers.ModelSerializer):
    effective_planning = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Department
        fields = [
            "id",
            "tenant",
            "organization",
            "parent",
            "planning",
            "effective_planning",
            "name",
            "code",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "effective_planning"]

    def get_effective_planning(self, obj):
        planning = obj.get_effective_planning()
        if planning is None:
            return None
        return {
            "id": planning.id,
            "tenant": planning.tenant_id,
            "name": planning.name,
            "code": planning.code,
        }

    def validate(self, attrs):
        tenant = attrs.get("tenant") or getattr(self.instance, "tenant", None)
        organization = attrs.get("organization") or getattr(self.instance, "organization", None)
        parent = attrs.get("parent") if "parent" in attrs else getattr(self.instance, "parent", None)
        planning = attrs.get("planning") if "planning" in attrs else getattr(self.instance, "planning", None)

        if tenant and organization and organization.tenant_id != tenant.id:
            raise serializers.ValidationError({"organization": "L'organisation doit appartenir au meme tenant."})
        if tenant and parent and parent.tenant_id != tenant.id:
            raise serializers.ValidationError({"parent": "Le parent doit appartenir au meme tenant."})
        if organization and parent and parent.organization_id != organization.id:
            raise serializers.ValidationError({"parent": "Le parent doit appartenir a la meme organisation."})
        if tenant and planning and planning.tenant_id != tenant.id:
            raise serializers.ValidationError({"planning": "Le planning doit appartenir au meme tenant."})

        return attrs
