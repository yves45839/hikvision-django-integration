from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from employees.models import Department, Employee, Organization, Planning
from employees.serializers import (
    DepartmentSerializer,
    EmployeeSerializer,
    OrganizationSerializer,
    PlanningSerializer,
)
from employees.services import build_card_info_payloads, build_user_info_payload
from hik_gateway.services.gateway_connection import get_shared_gateway_client


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

    @action(detail=True, methods=["post"], url_path="push-to-gateway")
    def push_to_gateway(self, request, pk=None):
        employee = self.get_object()

        dev_indexes = request.data.get("dev_indexes")
        if dev_indexes is None:
            dev_indexes = [dev.dev_index for dev in employee.devices.all() if dev.dev_index]
        if not isinstance(dev_indexes, list) or not dev_indexes:
            return Response(
                {"detail": "Fournis dev_indexes ou lie au moins un device a l'employee."},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
                errors.append({"dev_index": dev_index, "detail": str(exc)})

        output_status = status.HTTP_200_OK if not errors else status.HTTP_207_MULTI_STATUS
        return Response(
            {
                "status": "ok" if not errors else "partial",
                "employee_id": employee.id,
                "pushed": pushed,
                "errors": errors,
            },
            status=output_status,
        )
