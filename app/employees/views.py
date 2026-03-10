from __future__ import annotations

import json
import re
from datetime import timezone as dt_timezone

from django.http import HttpRequest
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from devices.models import Device
from employees.models import Department, Employee, Organization, Planning
from employees.serializers import (
    DepartmentSerializer,
    EmployeeSerializer,
    OrganizationSerializer,
    PlanningSerializer,
)
from employees.services import build_card_info_payloads, build_user_info_payload
from hik_gateway.services.gateway_connection import get_shared_gateway_client
from tenants.models import Tenant


class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.select_related("tenant").order_by("-id")
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant_code = str(self.request.query_params.get("tenant") or "").strip()
        if tenant_code:
            queryset = queryset.filter(tenant__code__iexact=tenant_code)
        return queryset


class PlanningViewSet(viewsets.ModelViewSet):
    queryset = Planning.objects.select_related("tenant").order_by("-id")
    serializer_class = PlanningSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant_code = str(self.request.query_params.get("tenant") or "").strip()
        if tenant_code:
            queryset = queryset.filter(tenant__code__iexact=tenant_code)
        return queryset


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = (
        Department.objects.select_related("tenant", "organization", "parent", "planning")
        .prefetch_related("employees")
        .order_by("-id")
    )
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant_code = str(self.request.query_params.get("tenant") or "").strip()
        if tenant_code:
            queryset = queryset.filter(tenant__code__iexact=tenant_code)
        organization_id = str(self.request.query_params.get("organization") or "").strip()
        if organization_id:
            queryset = queryset.filter(organization_id=organization_id)
        return queryset


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = (
        Employee.objects.select_related("tenant", "department", "face")
        .prefetch_related("attributes", "devices", "cards", "fingerprints")
        .order_by("-id")
    )
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant_code = str(self.request.query_params.get("tenant") or "").strip()
        if tenant_code:
            queryset = queryset.filter(tenant__code__iexact=tenant_code)
        return queryset

    def _push_employee(self, employee: Employee, dev_indexes: list[str] | None = None) -> dict:
        if dev_indexes is None:
            dev_indexes = [dev.dev_index for dev in employee.devices.all() if dev.dev_index]
        if not isinstance(dev_indexes, list) or not dev_indexes:
            return {
                "status": "skipped",
                "employee_id": employee.id,
                "pushed": [],
                "errors": [],
                "detail": "Aucun dev_index fourni ou lie a l'employee.",
            }

        client = get_shared_gateway_client(tenant_code=employee.tenant.code)
        user_payload = build_user_info_payload(employee)
        card_payloads = build_card_info_payloads(employee)

        pushed = []
        errors = []

        for dev_index in dev_indexes:
            try:
                user_response = client.add_access_user(dev_index=dev_index, payload=user_payload)
                card_response = []
                for card_payload in card_payloads:
                    card_response.append(client.add_access_card(dev_index=dev_index, payload=card_payload))
                pushed.append(
                    {
                        "dev_index": dev_index,
                        "user_response": user_response,
                        "card_response": card_response,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                detail = str(exc)
                if "employeeNoAlreadyExist" in detail:
                    pushed.append(
                        {
                            "dev_index": dev_index,
                            "user_response": {
                                "status": "already_exists",
                                "subStatusCode": "employeeNoAlreadyExist",
                            },
                            "card_response": [],
                        }
                    )
                    continue
                errors.append({"dev_index": dev_index, "detail": detail})

        return {
            "status": "ok" if not errors else "partial",
            "employee_id": employee.id,
            "pushed": pushed,
            "errors": errors,
        }

    @staticmethod
    def _parse_gateway_datetime(value: str | None):
        if not value:
            return None
        parsed = parse_datetime(value)
        if parsed is None:
            return None
        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed, timezone=dt_timezone.utc)
        return parsed

    @staticmethod
    def _to_attr_name(key: str) -> str:
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", str(key or "")).lower()
        snake = re.sub(r"[^a-z0-9_]+", "_", snake).strip("_")
        return f"gateway_{snake}" if snake else "gateway_unknown"

    @staticmethod
    def _to_attr_value(value) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        return str(value)

    @staticmethod
    def _to_int_or_none(value):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed or None

    def _sync_gateway_attributes(self, employee: Employee, row: dict):
        synced_names = set()
        for key, value in row.items():
            attr_name = self._to_attr_name(key)
            attr_value = self._to_attr_value(value)
            synced_names.add(attr_name)
            employee.attributes.update_or_create(
                name=attr_name,
                defaults={"value": attr_value},
            )
        # keep explicit user_type used by push payload
        user_type = str(row.get("userType") or "").strip()
        if user_type:
            employee.attributes.update_or_create(
                name="user_type",
                defaults={"value": user_type},
            )

    def create(self, request: HttpRequest, *args, **kwargs):
        tenant_id = request.data.get("tenant")
        employee_no = str(request.data.get("employee_no") or "").strip()
        existing = None
        if tenant_id and employee_no:
            existing = Employee.objects.filter(tenant_id=tenant_id, employee_no=employee_no).first()

        if existing is None:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            created = True
        else:
            serializer = self.get_serializer(existing, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            created = False

        employee = serializer.instance  # type: ignore[assignment]
        push_result = self._push_employee(employee)

        response_payload = dict(serializer.data)
        response_payload["gateway_push"] = push_result

        if push_result.get("status") in {"ok", "skipped"}:
            response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        else:
            response_status = status.HTTP_207_MULTI_STATUS
        headers = self.get_success_headers(serializer.data)
        return Response(response_payload, status=response_status, headers=headers)

    @action(detail=True, methods=["post"], url_path="push-to-gateway")
    def push_to_gateway(self, request, pk=None):
        employee = self.get_object()

        dev_indexes = request.data.get("dev_indexes")
        result = self._push_employee(employee, dev_indexes=dev_indexes)
        if result["status"] == "skipped":
            return Response(
                {"detail": "Fournis dev_indexes ou lie au moins un device a l'employee."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        output_status = status.HTTP_200_OK if result["status"] == "ok" else status.HTTP_207_MULTI_STATUS
        return Response(result, status=output_status)

    @action(detail=False, methods=["post"], url_path="import-from-gateway")
    def import_from_gateway(self, request):
        tenant_id = request.data.get("tenant")
        if not tenant_id:
            return Response({"detail": "Le champ tenant est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist:
            return Response({"detail": "Tenant introuvable."}, status=status.HTTP_404_NOT_FOUND)

        link_device = bool(request.data.get("link_device", True))
        max_results = int(request.data.get("max_results", 50))

        dev_indexes_input = request.data.get("dev_indexes")
        device_ids_input = request.data.get("device_ids")
        device_id_input = request.data.get("device_id")
        dev_index_input = request.data.get("dev_index")

        if dev_indexes_input is None:
            if dev_index_input:
                dev_indexes_input = [dev_index_input]
            elif device_ids_input is not None:
                dev_indexes_input = list(
                    Device.objects.filter(tenant=tenant, id__in=device_ids_input).values_list("dev_index", flat=True)
                )
            elif device_id_input is not None:
                dev_indexes_input = list(
                    Device.objects.filter(tenant=tenant, id=device_id_input).values_list("dev_index", flat=True)
                )
            else:
                dev_indexes_input = list(Device.objects.filter(tenant=tenant).values_list("dev_index", flat=True))

        if isinstance(dev_indexes_input, str):
            dev_indexes = [dev_indexes_input]
        elif isinstance(dev_indexes_input, list):
            dev_indexes = [str(item).strip() for item in dev_indexes_input if str(item).strip()]
        else:
            return Response({"detail": "dev_indexes doit etre une liste ou une chaine."}, status=status.HTTP_400_BAD_REQUEST)

        if not dev_indexes:
            return Response({"detail": "Aucun dev_index resolu pour l'import."}, status=status.HTTP_400_BAD_REQUEST)

        device_by_index = {
            device.dev_index: device
            for device in Device.objects.filter(tenant=tenant, dev_index__in=dev_indexes)
        }

        client = get_shared_gateway_client(tenant_code=tenant.code)
        created_count = 0
        updated_count = 0
        imported_count = 0
        errors = []
        imported = []

        for dev_index in dev_indexes:
            try:
                payload = client.search_access_users_all(dev_index=dev_index, max_results=max_results)
                search = payload.get("UserInfoSearch", {}) if isinstance(payload, dict) else {}
                users = search.get("UserInfo", []) if isinstance(search, dict) else []
                if isinstance(users, dict):
                    users = [users]
                if not isinstance(users, list):
                    users = []

                for row in users:
                    if not isinstance(row, dict):
                        continue
                    employee_no = str(row.get("employeeNo") or "").strip()
                    if not employee_no:
                        continue
                    name = str(row.get("name") or employee_no).strip()
                    valid = row.get("Valid", {}) if isinstance(row.get("Valid"), dict) else {}
                    valid_from = self._parse_gateway_datetime(valid.get("beginTime"))
                    valid_to = self._parse_gateway_datetime(valid.get("endTime"))
                    is_active = bool(valid.get("enable", True))

                    employee, was_created = Employee.objects.update_or_create(
                        tenant=tenant,
                        employee_no=employee_no,
                        defaults={
                            "name": name or employee_no,
                            "first_name": str(row.get("firstName") or "").strip(),
                            "last_name": str(row.get("lastName") or "").strip(),
                            "gender": str(row.get("gender") or "").strip(),
                            "email": str(row.get("email") or "").strip(),
                            "phone": str(row.get("phoneNo") or "").strip(),
                            "valid_from": valid_from,
                            "valid_to": valid_to,
                            "is_active": is_active,
                            "access_group": str(row.get("belongGroup") or "").strip(),
                            "pin_code": str(row.get("password") or "").strip(),
                            "only_authenticate": bool(row.get("onlyVerify", False)),
                            "extended_door_open_time": self._to_int_or_none(row.get("maxOpenDoorTime")),
                        },
                    )
                    if was_created:
                        created_count += 1
                    else:
                        updated_count += 1
                    imported_count += 1

                    self._sync_gateway_attributes(employee, row)

                    if link_device and dev_index in device_by_index:
                        employee.devices.add(device_by_index[dev_index])

                    imported.append(
                        {
                            "employee_id": employee.id,
                            "employee_no": employee.employee_no,
                            "name": employee.name,
                            "dev_index": dev_index,
                            "created": was_created,
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                errors.append({"dev_index": dev_index, "detail": str(exc)})

        response_status = status.HTTP_200_OK if not errors else status.HTTP_207_MULTI_STATUS
        return Response(
            {
                "status": "ok" if not errors else "partial",
                "tenant": tenant.id,
                "dev_indexes": dev_indexes,
                "imported_count": imported_count,
                "created_count": created_count,
                "updated_count": updated_count,
                "imported": imported,
                "errors": errors,
            },
            status=response_status,
        )
