from rest_framework import serializers

from devices.models import Device
from employees.models import (
    AccessGroup,
    Department,
    Employee,
    EmployeeAttribute,
    EmployeeCard,
    EmployeeFace,
    EmployeeFingerprint,
    Organization,
    Planning,
    PlanningAssignment,
    PlanningDailySlot,
    PlanningEntry,
    PlanningPeriod,
    LeaveRequest,
    WorkShift,
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


class PlanningDailySlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanningDailySlot
        fields = ["id", "day_of_week", "slot_type", "start_time", "end_time", "label", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class PlanningPeriodSerializer(serializers.ModelSerializer):
    work_shifts = serializers.PrimaryKeyRelatedField(many=True, queryset=WorkShift.objects.all(), required=False)
    shift_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = PlanningPeriod
        fields = [
            "id",
            "label",
            "start_date",
            "end_date",
            "work_shifts",
            "shift_count",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "shift_count", "created_at", "updated_at"]

    def get_shift_count(self, obj):
        return obj.work_shifts.count()


class PlanningEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanningEntry
        fields = [
            "id",
            "day_of_week",
            "sequence_index",
            "start_date",
            "end_date",
            "work_shift",
            "is_rest_day",
            "label",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PlanningAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanningAssignment
        fields = [
            "id",
            "tenant",
            "planning",
            "work_shift",
            "department",
            "employee",
            "valid_from",
            "valid_to",
            "include_sub_departments",
            "check_in_not_required",
            "check_out_not_required",
            "effective_for_holiday",
            "effective_for_overtime",
            "flexible_weekend",
            "priority",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        tenant = attrs.get("tenant") or getattr(self.instance, "tenant", None)
        planning = attrs.get("planning") if "planning" in attrs else getattr(self.instance, "planning", None)
        work_shift = attrs.get("work_shift") if "work_shift" in attrs else getattr(self.instance, "work_shift", None)
        department = attrs.get("department") if "department" in attrs else getattr(self.instance, "department", None)
        employee = attrs.get("employee") if "employee" in attrs else getattr(self.instance, "employee", None)

        if tenant and planning and planning.tenant_id != tenant.id:
            raise serializers.ValidationError({"planning": "Le planning doit appartenir au meme tenant."})
        if tenant and work_shift and work_shift.tenant_id != tenant.id:
            raise serializers.ValidationError({"work_shift": "Le quart doit appartenir au meme tenant."})
        if tenant and department and department.tenant_id != tenant.id:
            raise serializers.ValidationError({"department": "Le departement doit appartenir au meme tenant."})
        if tenant and employee and employee.tenant_id != tenant.id:
            raise serializers.ValidationError({"employee": "L'employee doit appartenir au meme tenant."})
        return attrs


class EmployeeSerializer(serializers.ModelSerializer):
    attributes = EmployeeAttributeSerializer(many=True, required=False)
    devices = serializers.PrimaryKeyRelatedField(many=True, queryset=Device.objects.all(), required=False)
    access_groups = serializers.PrimaryKeyRelatedField(many=True, queryset=AccessGroup.objects.all(), required=False)
    work_shifts = serializers.PrimaryKeyRelatedField(many=True, queryset=WorkShift.objects.all(), required=False)
    cards = EmployeeCardSerializer(many=True, required=False)
    fingerprints = EmployeeFingerprintSerializer(many=True, required=False)
    face = EmployeeFaceSerializer(required=False, allow_null=True)
    full_name = serializers.CharField(read_only=True)
    effective_planning = serializers.SerializerMethodField(read_only=True)
    effective_work_shift = serializers.SerializerMethodField(read_only=True)
    effective_work_shifts = serializers.SerializerMethodField(read_only=True)
    mobile_status = serializers.SerializerMethodField(read_only=True)
    require_credential = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Employee
        fields = [
            "id",
            "tenant",
            "devices",
            "device_assignment_mode",
            "access_groups",
            "department",
            "planning",
            "work_shift",
            "work_shifts",
            "employee_no",
            "name",
            "first_name",
            "last_name",
            "full_name",
            "effective_planning",
            "effective_work_shift",
            "effective_work_shifts",
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
            "mobile_status",
            "is_device_operator",
            "custom_profile",
            "only_authenticate",
            "date_of_birth",
            "identity_type",
            "identity_no",
            "position",
            "hire_date",
            "address",
            "needs_gateway_push",
            "last_gateway_push_at",
            "require_credential",
            "is_active",
            "attributes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "full_name",
            "effective_planning",
            "effective_work_shift",
            "effective_work_shifts",
            "needs_gateway_push",
            "last_gateway_push_at",
        ]
        extra_kwargs = {
            "name": {"allow_blank": False},
        }

    def get_mobile_status(self, obj) -> str:
        """linked (compte actif) | invited (invitation en attente) | none."""
        if obj.user_id is not None:
            return "linked"
        pending = getattr(obj, "_pending_mobile_invitations", None)
        if pending is None:
            pending = obj.mobile_invitations.filter(status="pending").exists()
        else:
            pending = bool(pending)
        return "invited" if pending else "none"

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

    def get_effective_work_shift(self, obj):
        shift = obj.effective_work_shift
        if shift is None:
            return None
        return self._serialize_shift(shift)

    def get_effective_work_shifts(self, obj):
        return [self._serialize_shift(shift) for shift in obj.effective_work_shifts]

    @staticmethod
    def _serialize_shift(shift):
        return {
            "id": shift.id,
            "tenant": shift.tenant_id,
            "name": shift.name,
            "code": shift.code,
            "start_time": shift.start_time,
            "end_time": shift.end_time,
            "break_start_time": shift.break_start_time,
            "break_end_time": shift.break_end_time,
            "overtime_minutes": shift.overtime_minutes,
            "late_allowable_minutes": shift.late_allowable_minutes,
            "early_leave_allowable_minutes": shift.early_leave_allowable_minutes,
        }

    def validate(self, attrs):
        tenant = attrs.get("tenant") or getattr(self.instance, "tenant", None)
        devices = attrs.get("devices")
        access_groups = attrs.get("access_groups")
        department = attrs.get("department") or getattr(self.instance, "department", None)
        planning = attrs.get("planning") if "planning" in attrs else getattr(self.instance, "planning", None)
        work_shift = attrs.get("work_shift") if "work_shift" in attrs else getattr(self.instance, "work_shift", None)
        work_shifts = attrs.get("work_shifts") if "work_shifts" in attrs else None
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
        if tenant and access_groups:
            invalid_group_ids = [group.id for group in access_groups if group.tenant_id != tenant.id]
            if invalid_group_ids:
                raise serializers.ValidationError(
                    {"access_groups": f"Groupes hors tenant: {invalid_group_ids}"}
                )

        if tenant and department and department.tenant_id != tenant.id:
            raise serializers.ValidationError({"department": "Le departement doit appartenir au meme tenant."})
        if tenant and planning and planning.tenant_id != tenant.id:
            raise serializers.ValidationError({"planning": "Le planning doit appartenir au meme tenant."})
        if tenant and work_shift and work_shift.tenant_id != tenant.id:
            raise serializers.ValidationError({"work_shift": "Le quart de travail doit appartenir au meme tenant."})
        if tenant and work_shifts is not None:
            invalid_shift_ids = [shift.id for shift in work_shifts if shift.tenant_id != tenant.id]
            if invalid_shift_ids:
                raise serializers.ValidationError({"work_shifts": f"Quarts hors tenant: {invalid_shift_ids}"})
        if work_shift is not None and work_shifts is not None:
            shift_ids = {shift.id for shift in work_shifts}
            if work_shift.id not in shift_ids:
                raise serializers.ValidationError(
                    {"work_shifts": "Le work_shift principal doit aussi figurer dans work_shifts."}
                )
        if self.instance is None and department is None:
            raise serializers.ValidationError({"department": "Le departement est obligatoire a la creation."})
        if self.instance is not None and "department" in attrs and attrs.get("department") is None:
            raise serializers.ValidationError({"department": "Le departement ne peut pas etre vide."})

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
        access_groups = validated_data.pop("access_groups", [])
        work_shifts = validated_data.pop("work_shifts", [])
        cards_data = validated_data.pop("cards", [])
        fingerprints_data = validated_data.pop("fingerprints", [])
        face_data = validated_data.pop("face", None)
        validated_data.pop("require_credential", None)

        employee = Employee.objects.create(**validated_data)
        if devices:
            employee.devices.set(devices)
        if access_groups:
            employee.access_groups.set(access_groups)
        if work_shift := validated_data.get("work_shift"):
            shift_ids = {shift.id for shift in work_shifts}
            if work_shift.id not in shift_ids:
                work_shifts = [*work_shifts, work_shift]
        if work_shifts:
            employee.work_shifts.set(work_shifts)
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
        access_groups = validated_data.pop("access_groups", None)
        work_shifts = validated_data.pop("work_shifts", None)
        cards_data = validated_data.pop("cards", None)
        fingerprints_data = validated_data.pop("fingerprints", None)
        face_data = validated_data.pop("face", serializers.empty)
        validated_data.pop("require_credential", None)
        # id is immutable on edit.
        validated_data.pop("id", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.needs_gateway_push = True
        instance.last_gateway_push_at = None
        instance.save()

        if devices is not None:
            instance.devices.set(devices)
        if access_groups is not None:
            instance.access_groups.set(access_groups)
        if work_shifts is not None:
            if instance.work_shift_id is not None:
                shift_ids = {shift.id for shift in work_shifts}
                if instance.work_shift_id not in shift_ids:
                    work_shifts = [*work_shifts, instance.work_shift]
            instance.work_shifts.set(work_shifts)
        elif instance.work_shift_id is not None:
            instance.work_shifts.add(instance.work_shift)

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
    daily_slots = PlanningDailySlotSerializer(many=True, required=False)
    periods = PlanningPeriodSerializer(many=True, required=False)
    entries = PlanningEntrySerializer(many=True, required=False)

    class Meta:
        model = Planning
        fields = [
            "id",
            "tenant",
            "name",
            "code",
            "description",
            "timezone",
            "metadata",
            "entries",
            "daily_slots",
            "periods",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        tenant = attrs.get("tenant") or getattr(self.instance, "tenant", None)
        entries = attrs.get("entries")
        periods = attrs.get("periods")
        if tenant and entries is not None:
            selector_groups = {}
            for idx, entry in enumerate(entries):
                work_shift = entry.get("work_shift")
                if work_shift and work_shift.tenant_id != tenant.id:
                    raise serializers.ValidationError(
                        {"entries": f"L'entree #{idx + 1} contient un quart hors tenant: {work_shift.id}"}
                    )
                selector = (
                    entry.get("day_of_week"),
                    entry.get("sequence_index"),
                    entry.get("start_date"),
                    entry.get("end_date"),
                )
                selector_groups.setdefault(selector, []).append(entry)

            for grouped_entries in selector_groups.values():
                has_rest_day = any(entry.get("is_rest_day") for entry in grouped_entries)
                has_work_shift = any(entry.get("work_shift") for entry in grouped_entries)
                if has_rest_day and has_work_shift:
                    raise serializers.ValidationError(
                        {"entries": "Un meme jour/segment ne peut pas contenir a la fois un repos et des shifts."}
                    )
        if tenant and periods is not None:
            ordered_periods = sorted(periods, key=lambda item: (item["start_date"], item["end_date"]))
            previous_period = None
            for idx, period in enumerate(periods):
                work_shifts = period.get("work_shifts", [])
                invalid_shift_ids = [shift.id for shift in work_shifts if shift.tenant_id != tenant.id]
                if invalid_shift_ids:
                    raise serializers.ValidationError(
                        {"periods": f"La periode #{idx + 1} contient des quarts hors tenant: {invalid_shift_ids}"}
                    )
            for period in ordered_periods:
                if period["end_date"] < period["start_date"]:
                    raise serializers.ValidationError(
                        {"periods": "Chaque periode doit avoir une date de fin superieure ou egale a la date de debut."}
                    )
                if previous_period is not None and period["start_date"] <= previous_period["end_date"]:
                    raise serializers.ValidationError(
                        {"periods": "Les periodes d'un planning ne doivent pas se chevaucher."}
                    )
                previous_period = period
        return attrs

    @staticmethod
    def _save_entries(planning, entries_data):
        for entry in entries_data:
            PlanningEntry.objects.create(planning=planning, **entry)

    @staticmethod
    def _save_periods(planning, periods_data):
        for period_data in periods_data:
            work_shifts = period_data.pop("work_shifts", [])
            period = PlanningPeriod.objects.create(planning=planning, **period_data)
            if work_shifts:
                period.work_shifts.set(work_shifts)

    def create(self, validated_data):
        entries = validated_data.pop("entries", [])
        daily_slots = validated_data.pop("daily_slots", [])
        periods = validated_data.pop("periods", [])
        planning = Planning.objects.create(**validated_data)
        self._save_entries(planning, entries)
        for slot in daily_slots:
            PlanningDailySlot.objects.create(planning=planning, **slot)
        self._save_periods(planning, periods)
        return planning

    def update(self, instance, validated_data):
        entries = validated_data.pop("entries", None)
        daily_slots = validated_data.pop("daily_slots", None)
        periods = validated_data.pop("periods", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if entries is not None:
            instance.entries.all().delete()
            self._save_entries(instance, entries)
        if daily_slots is not None:
            instance.daily_slots.all().delete()
            for slot in daily_slots:
                PlanningDailySlot.objects.create(planning=instance, **slot)
        if periods is not None:
            instance.periods.all().delete()
            self._save_periods(instance, periods)

        return instance


class DepartmentSerializer(serializers.ModelSerializer):
    effective_planning = serializers.SerializerMethodField(read_only=True)
    effective_work_shift = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Department
        fields = [
            "id",
            "tenant",
            "organization",
            "parent",
            "planning",
            "work_shift",
            "devices",
            "effective_planning",
            "effective_work_shift",
            "name",
            "code",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "effective_planning", "effective_work_shift"]
        extra_kwargs = {
            "code": {"required": False, "allow_blank": True},
        }

    def get_validators(self):
        # Remove the UniqueTogetherValidator for (organization, code) — the model's
        # save() auto-generates a unique code when none is provided, so this
        # validator would wrongly reject blank submissions before save() can run.
        return [
            v for v in super().get_validators()
            if not (hasattr(v, "fields") and set(v.fields) == {"organization", "code"})
        ]

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

    def get_effective_work_shift(self, obj):
        shift = obj.get_effective_work_shift()
        if shift is None:
            return None
        return {
            "id": shift.id,
            "tenant": shift.tenant_id,
            "name": shift.name,
            "code": shift.code,
            "start_time": shift.start_time,
            "end_time": shift.end_time,
            "break_start_time": shift.break_start_time,
            "break_end_time": shift.break_end_time,
            "overtime_minutes": shift.overtime_minutes,
            "late_allowable_minutes": shift.late_allowable_minutes,
            "early_leave_allowable_minutes": shift.early_leave_allowable_minutes,
        }

    def validate(self, attrs):
        tenant = attrs.get("tenant") or getattr(self.instance, "tenant", None)
        organization = attrs.get("organization") or getattr(self.instance, "organization", None)
        parent = attrs.get("parent") if "parent" in attrs else getattr(self.instance, "parent", None)
        planning = attrs.get("planning") if "planning" in attrs else getattr(self.instance, "planning", None)
        work_shift = attrs.get("work_shift") if "work_shift" in attrs else getattr(self.instance, "work_shift", None)
        devices = attrs.get("devices")

        if tenant and organization and organization.tenant_id != tenant.id:
            raise serializers.ValidationError({"organization": "L'organisation doit appartenir au meme tenant."})
        if tenant and parent and parent.tenant_id != tenant.id:
            raise serializers.ValidationError({"parent": "Le parent doit appartenir au meme tenant."})
        if organization and parent and parent.organization_id != organization.id:
            raise serializers.ValidationError({"parent": "Le parent doit appartenir a la meme organisation."})
        if tenant and planning and planning.tenant_id != tenant.id:
            raise serializers.ValidationError({"planning": "Le planning doit appartenir au meme tenant."})
        if tenant and work_shift and work_shift.tenant_id != tenant.id:
            raise serializers.ValidationError({"work_shift": "Le quart de travail doit appartenir au meme tenant."})
        if tenant and devices is not None:
            invalid_device_ids = [device.id for device in devices if device.tenant_id != tenant.id]
            if invalid_device_ids:
                raise serializers.ValidationError({"devices": f"Devices hors tenant: {invalid_device_ids}"})

        return attrs


class WorkShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkShift
        fields = [
            "id",
            "tenant",
            "name",
            "code",
            "description",
            "start_time",
            "end_time",
            "break_start_time",
            "break_end_time",
            "overtime_minutes",
            "late_allowable_minutes",
            "early_leave_allowable_minutes",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "code": {"required": False, "allow_blank": True},
            "start_time": {"required": False, "allow_null": True},
            "end_time": {"required": False, "allow_null": True},
            "break_start_time": {"required": False, "allow_null": True},
            "break_end_time": {"required": False, "allow_null": True},
            "overtime_minutes": {"required": False},
            "late_allowable_minutes": {"required": False},
            "early_leave_allowable_minutes": {"required": False},
        }


class AccessGroupSerializer(serializers.ModelSerializer):
    readers = serializers.PrimaryKeyRelatedField(many=True, queryset=Device.objects.all(), required=False)
    reader_count = serializers.SerializerMethodField(read_only=True)
    employee_count = serializers.SerializerMethodField(read_only=True)
    planning_name = serializers.CharField(source="planning.name", read_only=True)

    class Meta:
        model = AccessGroup
        fields = [
            "id",
            "tenant",
            "planning",
            "planning_name",
            "name",
            "code",
            "description",
            "readers",
            "reader_count",
            "employee_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "reader_count", "employee_count", "planning_name", "created_at", "updated_at"]

    def get_reader_count(self, obj):
        return obj.readers.count()

    def get_employee_count(self, obj):
        return obj.employees.count()

    def validate(self, attrs):
        tenant = attrs.get("tenant") or getattr(self.instance, "tenant", None)
        planning = attrs.get("planning") if "planning" in attrs else getattr(self.instance, "planning", None)
        readers = attrs.get("readers")

        if tenant and planning and planning.tenant_id != tenant.id:
            raise serializers.ValidationError({"planning": "Le planning doit appartenir au meme tenant."})

        if tenant and readers is not None:
            invalid_reader_ids = [reader.id for reader in readers if reader.tenant_id != tenant.id]
            if invalid_reader_ids:
                raise serializers.ValidationError({"readers": f"Lecteurs hors tenant: {invalid_reader_ids}"})

        return attrs

    def create(self, validated_data):
        readers = validated_data.pop("readers", [])
        access_group = AccessGroup.objects.create(**validated_data)
        if readers:
            access_group.readers.set(readers)
        return access_group

    def update(self, instance, validated_data):
        readers = validated_data.pop("readers", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if readers is not None:
            instance.readers.set(readers)
        return instance


class LeaveRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "tenant",
            "employee",
            "leave_type",
            "status",
            "start_date",
            "end_date",
            "reason",
            "rejection_reason",
            "approved_by",
            "approved_at",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        tenant = attrs.get("tenant") or getattr(self.instance, "tenant", None)
        employee = attrs.get("employee") if "employee" in attrs else getattr(self.instance, "employee", None)
        status_value = attrs.get("status") if "status" in attrs else getattr(self.instance, "status", LeaveRequest.STATUS_PENDING)
        approved_by = attrs.get("approved_by") if "approved_by" in attrs else getattr(self.instance, "approved_by", None)
        approved_at = attrs.get("approved_at") if "approved_at" in attrs else getattr(self.instance, "approved_at", None)
        start_date = attrs.get("start_date") if "start_date" in attrs else getattr(self.instance, "start_date", None)
        end_date = attrs.get("end_date") if "end_date" in attrs else getattr(self.instance, "end_date", None)

        if tenant and employee and employee.tenant_id != tenant.id:
            raise serializers.ValidationError({"employee": "L'employee doit appartenir au meme tenant."})
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({"end_date": "La date de fin doit etre superieure ou egale a la date de debut."})
        if status_value == LeaveRequest.STATUS_APPROVED:
            if approved_by is None:
                raise serializers.ValidationError({"approved_by": "approved_by est obligatoire quand le conge est approuve."})
            if approved_at is None:
                raise serializers.ValidationError({"approved_at": "approved_at est obligatoire quand le conge est approuve."})

        return attrs
