from __future__ import annotations

import json
import logging
import re
from hashlib import sha1
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone

from django.http import HttpRequest
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from devices.models import Device
from employees.models import (
    AccessGroup,
    Department,
    Employee,
    EmployeeCard,
    EmployeeFingerprint,
    LeaveRequest,
    Organization,
    OrganizationMembership,
    Planning,
    PlanningAssignment,
    WorkShift,
)
from employees.schedule_resolver import ScheduleResolver
from employees.serializers import (
    AccessGroupSerializer,
    DepartmentSerializer,
    EmployeeSerializer,
    LeaveRequestSerializer,
    OrganizationSerializer,
    PlanningAssignmentSerializer,
    PlanningSerializer,
    WorkShiftSerializer,
)
from employees.services import build_card_info_payloads, build_fingerprint_cfg_payloads, build_user_info_payload
from hik_gateway.services.gateway_connection import get_shared_gateway_client
from tenants.models import Tenant, TenantMembership, TenantRole
from tenants.services import has_tenant_role, scope_queryset_to_user_tenants

logger = logging.getLogger(__name__)


def _to_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _resolve_push_now(request: HttpRequest, default: bool = True) -> bool:
    query_value = request.query_params.get("push_now")
    if query_value is not None:
        return _to_bool(query_value, default=default)
    try:
        body_value = request.data.get("push_now")
    except Exception:  # noqa: BLE001
        body_value = None
    return _to_bool(body_value, default=default)


def _collect_department_subtree_ids(root_department_id: int) -> set[int]:
    subtree_ids = {root_department_id}
    frontier = [root_department_id]
    while frontier:
        children = list(
            Department.objects.filter(parent_id__in=frontier)
            .order_by("id")
            .values_list("id", flat=True)
        )
        frontier = [department_id for department_id in children if department_id not in subtree_ids]
        subtree_ids.update(frontier)
    return subtree_ids


def _auto_sync_employees_by_ids(employee_ids: list[int], *, push_now: bool = True) -> dict:
    normalized_ids = sorted({int(employee_id) for employee_id in employee_ids if employee_id})
    if not normalized_ids:
        return {
            "status": "skipped",
            "impacted_count": 0,
            "pushed_count": 0,
            "skipped_count": 0,
            "error_count": 0,
        }

    Employee.objects.filter(id__in=normalized_ids).update(
        needs_gateway_push=True,
        last_gateway_push_at=None,
        updated_at=timezone.now(),
    )

    if not push_now:
        return {
            "status": "queued",
            "impacted_count": len(normalized_ids),
            "pushed_count": 0,
            "skipped_count": len(normalized_ids),
            "error_count": 0,
        }

    employees = list(
        Employee.objects.filter(id__in=normalized_ids)
        .select_related("tenant", "department")
        .prefetch_related("devices", "department__devices", "cards", "fingerprints", "attributes", "access_groups__readers")
        .order_by("id")
    )

    pushed_count = 0
    skipped_count = 0
    errors = []

    for employee in employees:
        try:
            result = EmployeeViewSet._push_employee(employee)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "employee_id": employee.id,
                    "employee_no": employee.employee_no,
                    "detail": str(exc),
                }
            )
            continue

        result_status = result.get("status")
        if result_status == "ok":
            EmployeeViewSet._mark_gateway_push_success(employee)
            pushed_count += 1
            continue
        if result_status == "skipped":
            skipped_count += 1
            continue

        errors.append(
            {
                "employee_id": employee.id,
                "employee_no": employee.employee_no,
                "detail": "Gateway sync failed for employee.",
                "gateway_errors": result.get("errors", []),
            }
        )

    if errors:
        logger.warning("Automatic gateway sync completed with errors: %s", errors)

    return {
        "status": "ok" if not errors else "partial",
        "impacted_count": len(normalized_ids),
        "pushed_count": pushed_count,
        "skipped_count": skipped_count,
        "error_count": len(errors),
    }


def _auto_sync_employees_queryset(employees_qs, *, push_now: bool = True) -> dict:
    employee_ids = list(employees_qs.order_by("id").values_list("id", flat=True).distinct())
    return _auto_sync_employees_by_ids(employee_ids, push_now=push_now)


def _scope_to_request_tenants(queryset, request: HttpRequest, *, tenant_field: str = "tenant_id"):
    return scope_queryset_to_user_tenants(queryset, request.user, tenant_field=tenant_field)


def _require_tenant_scope(request: HttpRequest, tenant: Tenant | None, *, minimum_role: str = TenantRole.VIEWER) -> None:
    if tenant is None:
        raise PermissionDenied("Tenant is required for this action.")
    if has_tenant_role(request.user, tenant, minimum_role):
        return
    raise PermissionDenied("Insufficient tenant scope for this action.")


class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.select_related("tenant").order_by("-id")
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if not (user.is_superuser or user.is_staff):
            org_ids = OrganizationMembership.objects.filter(user=user).values_list("organization_id", flat=True)
            tenant_admin_ids = TenantMembership.objects.filter(
                user=user,
                role=TenantRole.TENANT_ADMIN,
            ).values_list("tenant_id", flat=True)
            queryset = queryset.filter(Q(id__in=org_ids) | Q(tenant_id__in=tenant_admin_ids)).distinct()
        tenant_code = str(self.request.query_params.get("tenant") or "").strip()
        if tenant_code:
            queryset = queryset.filter(tenant__code__iexact=tenant_code)
        return queryset

    def perform_create(self, serializer):
        tenant = serializer.validated_data.get("tenant")
        user = self.request.user
        if not has_tenant_role(user, tenant, TenantRole.ORG_ADMIN):
            raise PermissionDenied("Insufficient role to create an organization for this tenant.")
        serializer.save()

    def perform_update(self, serializer):
        instance = serializer.instance
        tenant = serializer.validated_data.get("tenant", instance.tenant)
        _require_tenant_scope(self.request, tenant)
        if serializer.validated_data.get("tenant") is not None and tenant.id != instance.tenant_id:
            raise PermissionDenied("Changing tenant is not allowed for this resource.")
        serializer.save()


class PlanningViewSet(viewsets.ModelViewSet):
    queryset = (
        Planning.objects.select_related("tenant")
        .prefetch_related("entries__work_shift", "daily_slots", "periods__work_shifts")
        .order_by("-id")
    )
    serializer_class = PlanningSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = _scope_to_request_tenants(super().get_queryset(), self.request, tenant_field="tenant_id")
        tenant_code = str(self.request.query_params.get("tenant") or "").strip()
        if tenant_code:
            queryset = queryset.filter(tenant__code__iexact=tenant_code)
        return queryset

    def perform_create(self, serializer):
        tenant = serializer.validated_data.get("tenant")
        _require_tenant_scope(self.request, tenant)
        serializer.save()

    def perform_update(self, serializer):
        instance = serializer.instance
        tenant = serializer.validated_data.get("tenant", instance.tenant)
        _require_tenant_scope(self.request, tenant)
        if serializer.validated_data.get("tenant") is not None and tenant.id != instance.tenant_id:
            raise PermissionDenied("Changing tenant is not allowed for this resource.")
        serializer.save()

    @staticmethod
    def _build_delete_usage(planning: Planning) -> dict:
        assigned_employees = Employee.objects.filter(planning=planning).order_by("id")
        assigned_departments = Department.objects.filter(planning=planning).order_by("id")
        linked_access_groups = AccessGroup.objects.filter(planning=planning).order_by("id")
        linked_assignments = PlanningAssignment.objects.filter(planning=planning).order_by("id")

        usage = {
            "planning_id": planning.id,
            "planning_name": planning.name,
            "assigned_employees_count": assigned_employees.count(),
            "assigned_departments_count": assigned_departments.count(),
            "linked_access_groups_count": linked_access_groups.count(),
            "linked_assignments_count": linked_assignments.count(),
            "assigned_employees": list(assigned_employees.values("id", "employee_no", "name")[:20]),
            "assigned_departments": list(assigned_departments.values("id", "code", "name")[:20]),
            "linked_access_groups": list(linked_access_groups.values("id", "code", "name")[:20]),
        }
        usage["has_links"] = any(
            [
                usage["assigned_employees_count"],
                usage["assigned_departments_count"],
                usage["linked_access_groups_count"],
                usage["linked_assignments_count"],
            ]
        )
        usage["can_delete_without_force"] = not usage["has_links"]
        return usage

    @action(detail=True, methods=["get"], url_path="delete-check")
    def delete_check(self, request, pk=None):
        planning = self.get_object()
        return Response(self._build_delete_usage(planning), status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        planning = self.get_object()
        usage = self._build_delete_usage(planning)
        force = _to_bool(request.query_params.get("force"), default=False)

        if usage["has_links"] and not force:
            return Response(
                {
                    "detail": "Le planning est encore lie a des enregistrements. Ajoute force=true pour supprimer.",
                    "usage": usage,
                },
                status=status.HTTP_409_CONFLICT,
            )

        self.perform_destroy(planning)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PlanningAssignmentViewSet(viewsets.ModelViewSet):
    queryset = (
        PlanningAssignment.objects.select_related("tenant", "planning", "work_shift", "department", "employee")
        .order_by("-id")
    )
    serializer_class = PlanningAssignmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = _scope_to_request_tenants(super().get_queryset(), self.request, tenant_field="tenant_id")
        tenant_code = str(self.request.query_params.get("tenant") or "").strip()
        if tenant_code:
            queryset = queryset.filter(tenant__code__iexact=tenant_code)
        employee_id = str(self.request.query_params.get("employee") or "").strip()
        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
        department_id = str(self.request.query_params.get("department") or "").strip()
        if department_id:
            queryset = queryset.filter(department_id=department_id)
        return queryset

    def perform_create(self, serializer):
        tenant = serializer.validated_data.get("tenant")
        _require_tenant_scope(self.request, tenant)
        serializer.save()

    def perform_update(self, serializer):
        instance = serializer.instance
        tenant = serializer.validated_data.get("tenant", instance.tenant)
        _require_tenant_scope(self.request, tenant)
        if serializer.validated_data.get("tenant") is not None and tenant.id != instance.tenant_id:
            raise PermissionDenied("Changing tenant is not allowed for this resource.")
        serializer.save()


class AccessGroupViewSet(viewsets.ModelViewSet):
    queryset = (
        AccessGroup.objects.select_related("tenant", "planning")
        .prefetch_related("readers", "employees")
        .order_by("-id")
    )
    serializer_class = AccessGroupSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = _scope_to_request_tenants(super().get_queryset(), self.request, tenant_field="tenant_id")
        tenant_code = str(self.request.query_params.get("tenant") or "").strip()
        if tenant_code:
            queryset = queryset.filter(tenant__code__iexact=tenant_code)
        return queryset

    def perform_create(self, serializer):
        tenant = serializer.validated_data.get("tenant")
        _require_tenant_scope(self.request, tenant)
        serializer.save()

    def perform_update(self, serializer):
        readers_updated = "readers" in serializer.validated_data
        instance = serializer.instance
        tenant = serializer.validated_data.get("tenant", instance.tenant)
        _require_tenant_scope(self.request, tenant)
        if serializer.validated_data.get("tenant") is not None and tenant.id != instance.tenant_id:
            raise PermissionDenied("Changing tenant is not allowed for this resource.")
        access_group = serializer.save()
        if not readers_updated:
            return
        _auto_sync_employees_queryset(
            access_group.employees.all(),
            push_now=_resolve_push_now(self.request, default=True),
        )

    def destroy(self, request, *args, **kwargs):
        access_group = self.get_object()
        impacted_employee_ids = list(access_group.employees.values_list("id", flat=True).distinct())
        self.perform_destroy(access_group)
        _auto_sync_employees_by_ids(
            impacted_employee_ids,
            push_now=_resolve_push_now(request, default=True),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkShiftViewSet(viewsets.ModelViewSet):
    queryset = WorkShift.objects.select_related("tenant").order_by("-id")
    serializer_class = WorkShiftSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = _scope_to_request_tenants(super().get_queryset(), self.request, tenant_field="tenant_id")
        tenant_code = str(self.request.query_params.get("tenant") or "").strip()
        if tenant_code:
            queryset = queryset.filter(tenant__code__iexact=tenant_code)
        return queryset

    def perform_create(self, serializer):
        tenant = serializer.validated_data.get("tenant")
        _require_tenant_scope(self.request, tenant)
        serializer.save()

    def perform_update(self, serializer):
        instance = serializer.instance
        tenant = serializer.validated_data.get("tenant", instance.tenant)
        _require_tenant_scope(self.request, tenant)
        if serializer.validated_data.get("tenant") is not None and tenant.id != instance.tenant_id:
            raise PermissionDenied("Changing tenant is not allowed for this resource.")
        serializer.save()

    @staticmethod
    def _build_delete_usage(work_shift: WorkShift) -> dict:
        assigned_users = (
            Employee.objects.filter(Q(work_shift=work_shift) | Q(work_shifts=work_shift))
            .distinct()
            .order_by("id")
        )
        departments = Department.objects.filter(work_shift=work_shift).order_by("id")
        assignments = PlanningAssignment.objects.filter(work_shift=work_shift).order_by("id")

        usage = {
            "work_shift_id": work_shift.id,
            "work_shift_name": work_shift.name,
            "assigned_users_count": assigned_users.count(),
            "assigned_as_main_shift_count": Employee.objects.filter(work_shift=work_shift).count(),
            "assigned_in_multi_shift_count": Employee.objects.filter(work_shifts=work_shift).distinct().count(),
            "assigned_departments_count": departments.count(),
            "linked_assignments_count": assignments.count(),
            "linked_planning_entries_count": work_shift.planning_entries.count(),
            "linked_planning_periods_count": work_shift.planning_periods.count(),
            "assigned_users": list(assigned_users.values("id", "employee_no", "name")[:20]),
            "assigned_departments": list(departments.values("id", "code", "name")[:20]),
        }
        usage["has_assigned_users"] = usage["assigned_users_count"] > 0
        usage["has_links"] = any(
            [
                usage["has_assigned_users"],
                usage["assigned_departments_count"],
                usage["linked_assignments_count"],
                usage["linked_planning_entries_count"],
                usage["linked_planning_periods_count"],
            ]
        )
        usage["can_delete_without_force"] = not usage["has_links"]
        return usage

    @action(detail=True, methods=["get"], url_path="delete-check")
    def delete_check(self, request, pk=None):
        work_shift = self.get_object()
        return Response(self._build_delete_usage(work_shift), status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        work_shift = self.get_object()
        usage = self._build_delete_usage(work_shift)
        force = _to_bool(request.query_params.get("force"), default=False)

        if usage["has_links"] and not force:
            return Response(
                {
                    "detail": (
                        "Ce quart est encore attribue (utilisateurs/departements/plannings). "
                        "Ajoute force=true pour supprimer."
                    ),
                    "usage": usage,
                },
                status=status.HTTP_409_CONFLICT,
            )

        self.perform_destroy(work_shift)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = (
        Department.objects.select_related("tenant", "organization", "parent", "planning", "work_shift")
        .prefetch_related("employees", "devices")
        .order_by("-id")
    )
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = _scope_to_request_tenants(super().get_queryset(), self.request, tenant_field="tenant_id")
        tenant_code = str(self.request.query_params.get("tenant") or "").strip()
        if tenant_code:
            queryset = queryset.filter(tenant__code__iexact=tenant_code)
        organization_id = str(self.request.query_params.get("organization") or "").strip()
        if organization_id:
            queryset = queryset.filter(organization_id=organization_id)
        return queryset

    def perform_create(self, serializer):
        tenant = serializer.validated_data.get("tenant")
        _require_tenant_scope(self.request, tenant)
        serializer.save()

    def perform_update(self, serializer):
        should_sync = any(field in serializer.validated_data for field in ("devices", "parent"))
        instance = serializer.instance
        tenant = serializer.validated_data.get("tenant", instance.tenant)
        _require_tenant_scope(self.request, tenant)
        if serializer.validated_data.get("tenant") is not None and tenant.id != instance.tenant_id:
            raise PermissionDenied("Changing tenant is not allowed for this resource.")
        department = serializer.save()
        if not should_sync:
            return
        subtree_ids = _collect_department_subtree_ids(department.id)
        _auto_sync_employees_queryset(
            Employee.objects.filter(department_id__in=subtree_ids),
            push_now=_resolve_push_now(self.request, default=True),
        )

    def destroy(self, request, *args, **kwargs):
        department = self.get_object()
        subtree_ids = _collect_department_subtree_ids(department.id)
        impacted_employee_ids = list(
            Employee.objects.filter(department_id__in=subtree_ids).values_list("id", flat=True).distinct()
        )
        self.perform_destroy(department)
        _auto_sync_employees_by_ids(
            impacted_employee_ids,
            push_now=_resolve_push_now(request, default=True),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _upsert_department_assignment(department: Department, *, planning=None, work_shift=None, include_sub_departments=False):
        today = timezone.localdate()
        assignment = (
            PlanningAssignment.objects.filter(
                tenant=department.tenant,
                department=department,
                valid_to__isnull=True,
            )
            .order_by("-valid_from", "-priority", "-id")
            .first()
        )
        if assignment is None:
            assignment = PlanningAssignment(
                tenant=department.tenant,
                department=department,
                valid_from=today,
            )
        assignment.include_sub_departments = include_sub_departments
        if planning is not None:
            assignment.planning = planning
        if work_shift is not None:
            assignment.work_shift = work_shift
        assignment.save()
        return assignment

    @action(detail=True, methods=["post"], url_path="assign-planning")
    def assign_planning(self, request, pk=None):
        department = self.get_object()
        planning_id = request.data.get("planning")
        if not planning_id:
            return Response({"detail": "Le champ planning est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            planning = Planning.objects.get(id=planning_id)
        except Planning.DoesNotExist:
            return Response({"detail": "Planning introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if planning.tenant_id != department.tenant_id:
            return Response(
                {"detail": "Le planning doit appartenir au meme tenant que le departement."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        include_sub_departments = EmployeeViewSet._to_bool(
            request.data.get("include_sub_departments"),
            default=False,
        )
        self._upsert_department_assignment(
            department,
            planning=planning,
            include_sub_departments=include_sub_departments,
        )
        department.planning = planning
        department.save(update_fields=["planning", "updated_at"])
        return Response(self.get_serializer(department).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="assign-work-shift")
    def assign_work_shift(self, request, pk=None):
        department = self.get_object()
        work_shift_id = request.data.get("work_shift")
        if not work_shift_id:
            return Response({"detail": "Le champ work_shift est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            work_shift = WorkShift.objects.get(id=work_shift_id)
        except WorkShift.DoesNotExist:
            return Response({"detail": "Quart de travail introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if work_shift.tenant_id != department.tenant_id:
            return Response(
                {"detail": "Le quart de travail doit appartenir au meme tenant que le departement."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        include_sub_departments = EmployeeViewSet._to_bool(
            request.data.get("include_sub_departments"),
            default=False,
        )
        self._upsert_department_assignment(
            department,
            work_shift=work_shift,
            include_sub_departments=include_sub_departments,
        )
        department.work_shift = work_shift
        department.save(update_fields=["work_shift", "updated_at"])
        return Response(self.get_serializer(department).data, status=status.HTTP_200_OK)


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = (
        Employee.objects.select_related("tenant", "department", "planning", "work_shift", "face")
        .prefetch_related(
            "attributes",
            "devices",
            "department__devices",
            "cards",
            "fingerprints",
            "access_groups__readers",
            "work_shifts",
        )
        .order_by("-id")
    )
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = _scope_to_request_tenants(super().get_queryset(), self.request, tenant_field="tenant_id")
        tenant_code = str(self.request.query_params.get("tenant") or "").strip()
        if tenant_code:
            queryset = queryset.filter(tenant__code__iexact=tenant_code)
        pending_only = self._to_bool(self.request.query_params.get("pending_only"), default=False)
        if pending_only:
            queryset = queryset.filter(needs_gateway_push=True)
        return queryset

    def perform_create(self, serializer):
        tenant = serializer.validated_data.get("tenant")
        _require_tenant_scope(self.request, tenant)
        serializer.save()

    def perform_update(self, serializer):
        instance = serializer.instance
        tenant = serializer.validated_data.get("tenant", instance.tenant)
        _require_tenant_scope(self.request, tenant)
        if serializer.validated_data.get("tenant") is not None and tenant.id != instance.tenant_id:
            raise PermissionDenied("Changing tenant is not allowed for this resource.")
        serializer.save()

    @staticmethod
    def _upsert_employee_assignment(employee: Employee, *, planning=None, work_shift=None):
        today = timezone.localdate()
        assignment = (
            PlanningAssignment.objects.filter(
                tenant=employee.tenant,
                employee=employee,
                valid_to__isnull=True,
            )
            .order_by("-valid_from", "-priority", "-id")
            .first()
        )
        if assignment is None:
            assignment = PlanningAssignment(
                tenant=employee.tenant,
                employee=employee,
                valid_from=today,
            )
        if planning is not None:
            assignment.planning = planning
        if work_shift is not None:
            assignment.work_shift = work_shift
        assignment.save()
        return assignment

    @staticmethod
    def _mark_gateway_push_success(employee: Employee):
        Employee.objects.filter(id=employee.id).update(
            needs_gateway_push=False,
            last_gateway_push_at=timezone.now(),
        )

    def _push_or_defer_employee(self, employee: Employee, push_now: bool) -> dict:
        if not push_now:
            return {
                "status": "deferred",
                "employee_id": employee.id,
                "pushed": [],
                "errors": [],
                "detail": "Push differe. Utilise /push-to-gateway/ ou /push-pending/ quand pret.",
            }

        push_result = self._push_employee(employee)
        if push_result.get("status") == "ok":
            self._mark_gateway_push_success(employee)
            employee.refresh_from_db()
        return push_result

    def _response_with_auto_sync(self, request: HttpRequest, employee: Employee, payload: dict) -> Response:
        push_now = self._to_bool(request.data.get("push_now"), default=True)
        push_result = self._push_or_defer_employee(employee, push_now=push_now)
        payload["gateway_push"] = push_result
        response_status = (
            status.HTTP_200_OK
            if push_result.get("status") in {"ok", "skipped", "deferred"}
            else status.HTTP_207_MULTI_STATUS
        )
        return Response(payload, status=response_status)

    @staticmethod
    def _push_employee(employee: Employee, dev_indexes: list[str] | None = None) -> dict:
        if dev_indexes is None:
            dev_indexes = []
            for device in employee.get_effective_devices(include_department_ancestors=True):
                dev_index = str(device.dev_index or "").strip()
                if dev_index:
                    dev_indexes.append(dev_index)
        elif isinstance(dev_indexes, list):
            dev_indexes = [str(item).strip() for item in dev_indexes if str(item).strip()]

        if isinstance(dev_indexes, list):
            dev_indexes = list(dict.fromkeys(dev_indexes))
        if not isinstance(dev_indexes, list) or not dev_indexes:
            return {
                "status": "skipped",
                "employee_id": employee.id,
                "pushed": [],
                "errors": [],
                "detail": "Aucun dev_index fourni ou resolu via la configuration employee/departement.",
            }

        client = get_shared_gateway_client(tenant_code=employee.tenant.code)
        user_payload = build_user_info_payload(employee)
        card_payloads = build_card_info_payloads(employee)
        fingerprint_payloads = build_fingerprint_cfg_payloads(employee)

        pushed = []
        errors = []

        for dev_index in dev_indexes:
            user_response = None
            try:
                user_response = client.add_access_user(dev_index=dev_index, payload=user_payload)
            except Exception as exc:  # noqa: BLE001
                detail = str(exc)
                if "employeeNoAlreadyExist" in detail:
                    user_response = {
                        "status": "already_exists",
                        "subStatusCode": "employeeNoAlreadyExist",
                    }
                else:
                    errors.append({"dev_index": dev_index, "detail": detail})
                    continue

            card_response = []
            card_errors = []
            for card_payload in card_payloads:
                try:
                    card_response.append(client.add_access_card(dev_index=dev_index, payload=card_payload))
                except Exception as exc:  # noqa: BLE001
                    detail = str(exc)
                    if "cardNoAlreadyExist" in detail:
                        card_response.append(
                            {
                                "status": "already_exists",
                                "subStatusCode": "cardNoAlreadyExist",
                            }
                        )
                        continue
                    card_errors.append(
                        {
                            "detail": detail,
                            "card_no": (
                                card_payload.get("CardInfo", {}).get("cardNo")
                                if isinstance(card_payload, dict)
                                else None
                            ),
                        }
                    )

            fingerprint_response = []
            fingerprint_errors = []
            for fingerprint_payload in fingerprint_payloads:
                try:
                    fingerprint_response.append(
                        client.add_access_fingerprint(dev_index=dev_index, payload=fingerprint_payload)
                    )
                except Exception as exc:  # noqa: BLE001
                    detail = str(exc)
                    normalized_detail = detail.lower()
                    if "fingerprintidalreadyexist" in normalized_detail or "fingerprintalreadyexist" in normalized_detail:
                        fingerprint_response.append(
                            {
                                "status": "already_exists",
                                "subStatusCode": "fingerPrintIDAlreadyExist",
                            }
                        )
                        continue
                    fingerprint_errors.append(
                        {
                            "detail": detail,
                            "finger_index": (
                                fingerprint_payload.get("FingerPrintCfg", {}).get("fingerPrintID")
                                if isinstance(fingerprint_payload, dict)
                                else None
                            ),
                        }
                    )

            pushed.append(
                {
                    "dev_index": dev_index,
                    "user_response": user_response,
                    "card_response": card_response,
                    "fingerprint_response": fingerprint_response,
                }
            )
            if card_errors:
                errors.append(
                    {
                        "dev_index": dev_index,
                        "detail": "One or more card pushes failed.",
                        "card_errors": card_errors,
                    }
                )
            if fingerprint_errors:
                errors.append(
                    {
                        "dev_index": dev_index,
                        "detail": "One or more fingerprint pushes failed.",
                        "fingerprint_errors": fingerprint_errors,
                    }
                )

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
        raw = f"gateway_{snake}" if snake else "gateway_unknown"
        if len(raw) <= 64:
            return raw
        digest = sha1(raw.encode("utf-8")).hexdigest()[:8]
        keep = 64 - len(digest) - 1
        return f"{raw[:keep]}_{digest}"

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

    @staticmethod
    def _to_bool(value, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off"}:
            return False
        return default

    @staticmethod
    def _parse_gateway_date(value: str | None):
        if not value:
            return None
        parsed = parse_date(str(value))
        return parsed

    @staticmethod
    def _duration_minutes(start_time, end_time):
        if not start_time or not end_time:
            return 0
        start_dt = datetime.combine(date.today(), start_time)
        end_dt = datetime.combine(date.today(), end_time)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
        return int((end_dt - start_dt).total_seconds() // 60)

    @staticmethod
    def _serialize_work_shift(shift: WorkShift):
        total_minutes = EmployeeViewSet._duration_minutes(shift.start_time, shift.end_time)
        break_minutes = EmployeeViewSet._duration_minutes(shift.break_start_time, shift.break_end_time)
        net_minutes = max(total_minutes - break_minutes, 0)
        return {
            "id": shift.id,
            "name": shift.name,
            "code": shift.code,
            "description": shift.description,
            "start_time": shift.start_time,
            "end_time": shift.end_time,
            "break_start_time": shift.break_start_time,
            "break_end_time": shift.break_end_time,
            "overtime_minutes": shift.overtime_minutes,
            "late_allowable_minutes": shift.late_allowable_minutes,
            "early_leave_allowable_minutes": shift.early_leave_allowable_minutes,
            "total_minutes": total_minutes,
            "net_minutes": net_minutes,
        }

    @staticmethod
    def _serialize_reader(device: Device):
        return {
            "id": device.id,
            "dev_index": device.dev_index,
            "serial_number": device.serial_number,
            "name": device.name,
            "status": device.status,
        }

    def _iter_attr_pairs(self, key: str, value):
        attr_name = self._to_attr_name(key)
        yield attr_name, self._to_attr_value(value)
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                child_name = f"{key}_{child_key}" if key else str(child_key)
                yield from self._iter_attr_pairs(child_name, child_value)
        elif isinstance(value, list):
            for idx, child_value in enumerate(value):
                child_name = f"{key}_{idx}" if key else str(idx)
                yield from self._iter_attr_pairs(child_name, child_value)

    def _sync_gateway_attributes(self, employee: Employee, row: dict):
        for key, value in row.items():
            for attr_name, attr_value in self._iter_attr_pairs(str(key), value):
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
        door_right = str(row.get("doorRight") or "").strip()
        if door_right:
            employee.attributes.update_or_create(
                name="door_right",
                defaults={"value": door_right},
            )
        right_plan = row.get("RightPlan")
        if isinstance(right_plan, dict):
            right_plan = [right_plan]
        if isinstance(right_plan, list) and right_plan:
            first_plan = right_plan[0] if isinstance(right_plan[0], dict) else {}
            if first_plan:
                door_no = str(first_plan.get("doorNo") or "").strip()
                plan_template_no = str(first_plan.get("planTemplateNo") or "").strip()
                if door_no:
                    employee.attributes.update_or_create(
                        name="door_no",
                        defaults={"value": door_no},
                    )
                if plan_template_no:
                    employee.attributes.update_or_create(
                        name="plan_template_no",
                        defaults={"value": plan_template_no},
                    )

    @action(detail=True, methods=["get"], url_path="schedule")
    def schedule(self, request, pk=None):
        employee = self.get_object()
        month_value = str(request.query_params.get("month") or "").strip()

        if month_value:
            try:
                month_start = datetime.strptime(month_value, "%Y-%m").date().replace(day=1)
            except ValueError:
                return Response(
                    {"detail": "Le parametre month doit etre au format YYYY-MM."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            today = timezone.localdate()
            month_start = today.replace(day=1)
        payload = ScheduleResolver().build_month_schedule(employee, month_start)
        payload["employee"]["department"] = employee.department.name if employee.department_id else None
        payload["month_label"] = month_start.strftime("%B %Y")
        payload["previous_month"] = (month_start - timedelta(days=1)).replace(day=1).strftime("%Y-%m")
        last_day = monthrange(month_start.year, month_start.month)[1]
        month_end = month_start.replace(day=last_day)
        payload["next_month"] = (month_end + timedelta(days=1)).replace(day=1).strftime("%Y-%m")
        for day in payload["days"]:
            current_date = datetime.strptime(day["date"], "%Y-%m-%d").date()
            day["day_of_week"] = day.pop("weekday")
            day["day_name"] = current_date.strftime("%A")
        return Response(payload, status=status.HTTP_200_OK)

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
        push_now = self._to_bool(request.data.get("push_now"), default=True)
        push_result = self._push_or_defer_employee(employee, push_now=push_now)

        response_payload = dict(self.get_serializer(employee).data)
        response_payload["gateway_push"] = push_result

        if push_result.get("status") in {"ok", "skipped", "deferred"}:
            response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        else:
            response_status = status.HTTP_207_MULTI_STATUS
        headers = self.get_success_headers(serializer.data)
        return Response(response_payload, status=response_status, headers=headers)

    def update(self, request: HttpRequest, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}

        employee = serializer.instance  # type: ignore[assignment]
        push_now = self._to_bool(request.data.get("push_now"), default=True)
        push_result = self._push_or_defer_employee(employee, push_now=push_now)

        response_payload = dict(self.get_serializer(employee).data)
        response_payload["gateway_push"] = push_result
        response_status = (
            status.HTTP_200_OK
            if push_result.get("status") in {"ok", "skipped", "deferred"}
            else status.HTTP_207_MULTI_STATUS
        )
        return Response(response_payload, status=response_status)

    def partial_update(self, request: HttpRequest, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="push-to-gateway")
    def push_to_gateway(self, request, pk=None):
        employee = self.get_object()

        dev_indexes = request.data.get("dev_indexes")
        result = self._push_employee(employee, dev_indexes=dev_indexes)
        if result["status"] == "skipped":
            return Response(
                {
                    **result,
                    "detail": "Fournis dev_indexes ou configure des pointeuses au niveau employee/departement.",
                },
                status=status.HTTP_200_OK,
            )
        if result["status"] == "ok":
            self._mark_gateway_push_success(employee)
        output_status = status.HTTP_200_OK if result["status"] == "ok" else status.HTTP_207_MULTI_STATUS
        return Response(result, status=output_status)

    @action(detail=True, methods=["post"], url_path="move-department")
    def move_department(self, request, pk=None):
        employee = self.get_object()
        department_id = request.data.get("department")
        if not department_id:
            return Response({"detail": "Le champ department est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            department = Department.objects.get(id=department_id)
        except Department.DoesNotExist:
            return Response({"detail": "Departement introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if department.tenant_id != employee.tenant_id:
            return Response(
                {"detail": "Le departement cible doit appartenir au meme tenant que l'employee."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        employee.department = department
        employee.needs_gateway_push = True
        employee.last_gateway_push_at = None
        employee.save(update_fields=["department", "needs_gateway_push", "last_gateway_push_at", "updated_at"])
        response_payload = dict(self.get_serializer(employee).data)
        return self._response_with_auto_sync(request, employee, response_payload)

    @action(detail=True, methods=["post"], url_path="assign-devices")
    def assign_devices(self, request, pk=None):
        employee = self.get_object()
        device_ids = request.data.get("devices")
        replace = self._to_bool(request.data.get("replace"), default=True)
        mode_provided = "device_assignment_mode" in request.data
        mode = str(request.data.get("device_assignment_mode") or "").strip()

        if device_ids is None:
            device_ids = []
        if not isinstance(device_ids, list):
            return Response({"detail": "Le champ devices doit etre une liste."}, status=status.HTTP_400_BAD_REQUEST)

        valid_modes = {choice[0] for choice in Employee.DEVICE_ASSIGNMENT_MODE_CHOICES}
        if mode_provided and mode not in valid_modes:
            return Response({"detail": "device_assignment_mode invalide."}, status=status.HTTP_400_BAD_REQUEST)

        selected_devices = list(Device.objects.filter(tenant=employee.tenant, id__in=device_ids).order_by("id"))
        found_ids = {device.id for device in selected_devices}
        missing_ids = [device_id for device_id in device_ids if device_id not in found_ids]
        if missing_ids:
            return Response(
                {"detail": f"Lecteurs introuvables pour ce tenant: {missing_ids}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if replace:
            employee.devices.set(selected_devices)
        else:
            employee.devices.add(*selected_devices)

        update_fields = ["needs_gateway_push", "last_gateway_push_at", "updated_at"]
        if mode_provided:
            employee.device_assignment_mode = mode
            update_fields.append("device_assignment_mode")
        employee.needs_gateway_push = True
        employee.last_gateway_push_at = None
        employee.save(update_fields=update_fields)

        response_payload = dict(self.get_serializer(employee).data)
        response_payload["reader_selection"] = {
            "device_assignment_mode": employee.device_assignment_mode,
            "employee_readers": [self._serialize_reader(reader) for reader in employee.devices.order_by("id")],
            "effective_readers": [
                self._serialize_reader(reader)
                for reader in employee.get_effective_devices(include_department_ancestors=True)
            ],
        }
        return self._response_with_auto_sync(request, employee, response_payload)

    @action(detail=True, methods=["post"], url_path="assign-access-groups")
    def assign_access_groups(self, request, pk=None):
        employee = self.get_object()
        access_group_ids = request.data.get("access_groups")
        replace = self._to_bool(request.data.get("replace"), default=True)

        if access_group_ids is None:
            access_group_ids = []
        if not isinstance(access_group_ids, list):
            return Response({"detail": "Le champ access_groups doit etre une liste."}, status=status.HTTP_400_BAD_REQUEST)

        groups = list(AccessGroup.objects.filter(tenant=employee.tenant, id__in=access_group_ids).order_by("id"))
        found_ids = {group.id for group in groups}
        missing_ids = [group_id for group_id in access_group_ids if group_id not in found_ids]
        if missing_ids:
            return Response(
                {"detail": f"Groupes d'acces introuvables pour ce tenant: {missing_ids}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if replace:
            employee.access_groups.set(groups)
        else:
            employee.access_groups.add(*groups)

        employee.needs_gateway_push = True
        employee.last_gateway_push_at = None
        employee.save(update_fields=["needs_gateway_push", "last_gateway_push_at", "updated_at"])

        response_payload = dict(self.get_serializer(employee).data)
        response_payload["access_group_selection"] = {
            "employee_access_groups": [
                {
                    "id": group.id,
                    "name": group.name,
                    "code": group.code,
                    "reader_count": group.readers.count(),
                }
                for group in employee.access_groups.order_by("id")
            ]
        }
        return self._response_with_auto_sync(request, employee, response_payload)

    @action(detail=True, methods=["post"], url_path="assign-planning")
    def assign_planning(self, request, pk=None):
        employee = self.get_object()
        planning_id = request.data.get("planning")
        if not planning_id:
            return Response({"detail": "Le champ planning est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            planning = Planning.objects.get(id=planning_id)
        except Planning.DoesNotExist:
            return Response({"detail": "Planning introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if planning.tenant_id != employee.tenant_id:
            return Response(
                {"detail": "Le planning doit appartenir au meme tenant que l'employee."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reader_ids_provided = "reader_ids" in request.data
        reader_ids_value = request.data.get("reader_ids")
        device_mode_provided = "device_assignment_mode" in request.data
        device_mode_value = str(request.data.get("device_assignment_mode") or "").strip()
        confirm_reader_selection = self._to_bool(request.data.get("confirm_reader_selection"), default=False)

        valid_modes = {choice[0] for choice in Employee.DEVICE_ASSIGNMENT_MODE_CHOICES}
        if device_mode_provided and device_mode_value not in valid_modes:
            return Response(
                {"detail": "device_assignment_mode invalide."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        selected_readers = None
        if reader_ids_provided:
            if reader_ids_value is None:
                reader_ids_value = []
            if not isinstance(reader_ids_value, list):
                return Response({"detail": "reader_ids doit etre une liste."}, status=status.HTTP_400_BAD_REQUEST)

            selected_readers = list(Device.objects.filter(tenant=employee.tenant, id__in=reader_ids_value).order_by("id"))
            found_reader_ids = {reader.id for reader in selected_readers}
            missing_reader_ids = [reader_id for reader_id in reader_ids_value if reader_id not in found_reader_ids]
            if missing_reader_ids:
                return Response(
                    {"detail": f"Lecteurs introuvables pour ce tenant: {missing_reader_ids}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        should_prompt_reader_selection = not confirm_reader_selection and not reader_ids_provided and not device_mode_provided

        self._upsert_employee_assignment(employee, planning=planning)
        employee.planning = planning
        update_fields = ["planning", "needs_gateway_push", "last_gateway_push_at", "updated_at"]
        if device_mode_provided:
            employee.device_assignment_mode = device_mode_value
            update_fields.append("device_assignment_mode")
        employee.needs_gateway_push = True
        employee.last_gateway_push_at = None
        employee.save(update_fields=update_fields)
        if selected_readers is not None:
            employee.devices.set(selected_readers)

        response_payload = dict(self.get_serializer(employee).data)
        response_payload["reader_selection"] = {
            "device_assignment_mode": employee.device_assignment_mode,
            "employee_readers": [self._serialize_reader(reader) for reader in employee.devices.order_by("id")],
            "effective_readers": [
                self._serialize_reader(reader)
                for reader in employee.get_effective_devices(include_department_ancestors=True)
            ],
        }
        if should_prompt_reader_selection:
            available_readers = list(Device.objects.filter(tenant=employee.tenant).order_by("id"))
            response_payload["reader_selection_prompt"] = {
                "detail": (
                    "Indique le ou les lecteurs qui serviront de points de pointage "
                    "avec reader_ids, et eventuellement le device_assignment_mode."
                ),
                "reader_selection_required": True,
                "device_assignment_mode": employee.device_assignment_mode,
                "available_readers": [self._serialize_reader(reader) for reader in available_readers],
            }
        return self._response_with_auto_sync(request, employee, response_payload)

    @action(detail=True, methods=["post"], url_path="assign-plannings")
    def assign_plannings(self, request, pk=None):
        employee = self.get_object()
        planning_ids = request.data.get("plannings")
        replace = self._to_bool(request.data.get("replace"), default=True)

        if not isinstance(planning_ids, list) or not planning_ids:
            return Response(
                {"detail": "Le champ plannings est obligatoire et doit etre une liste non vide."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        unique_ids = []
        seen = set()
        for planning_id in planning_ids:
            try:
                parsed_id = int(planning_id)
            except (TypeError, ValueError):
                return Response(
                    {"detail": f"Identifiant de planning invalide: {planning_id}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if parsed_id in seen:
                continue
            seen.add(parsed_id)
            unique_ids.append(parsed_id)

        planning_lookup = {
            planning.id: planning
            for planning in Planning.objects.filter(id__in=unique_ids).order_by("id")
        }
        missing_ids = [planning_id for planning_id in unique_ids if planning_id not in planning_lookup]
        if missing_ids:
            return Response(
                {"detail": f"Plannings introuvables: {missing_ids}."},
                status=status.HTTP_404_NOT_FOUND,
            )

        plannings = [planning_lookup[planning_id] for planning_id in unique_ids]
        invalid_ids = [planning.id for planning in plannings if planning.tenant_id != employee.tenant_id]
        if invalid_ids:
            return Response(
                {"detail": f"Les plannings {invalid_ids} doivent appartenir au meme tenant que l'employee."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.localdate()
        if replace:
            (
                PlanningAssignment.objects.filter(
                    tenant=employee.tenant,
                    employee=employee,
                    valid_to__isnull=True,
                )
                .exclude(planning_id__isnull=True)
                .update(valid_to=today)
            )

        existing_assignments = {
            assignment.planning_id: assignment
            for assignment in PlanningAssignment.objects.filter(
                tenant=employee.tenant,
                employee=employee,
                valid_to__isnull=True,
                planning_id__in=unique_ids,
            ).order_by("-priority", "-id")
        }

        total_plannings = len(plannings)
        for index, planning in enumerate(plannings):
            assignment = existing_assignments.get(planning.id)
            if assignment is None:
                assignment = PlanningAssignment(
                    tenant=employee.tenant,
                    employee=employee,
                    planning=planning,
                    valid_from=today,
                )
            else:
                assignment.planning = planning
                assignment.valid_to = None
            assignment.priority = total_plannings - index
            assignment.save()

        employee.planning = plannings[0]
        employee.needs_gateway_push = True
        employee.last_gateway_push_at = None
        employee.save(update_fields=["planning", "needs_gateway_push", "last_gateway_push_at", "updated_at"])
        response_payload = dict(self.get_serializer(employee).data)
        return self._response_with_auto_sync(request, employee, response_payload)

    @action(detail=True, methods=["post"], url_path="assign-work-shift")
    def assign_work_shift(self, request, pk=None):
        employee = self.get_object()
        work_shift_id = request.data.get("work_shift")
        if not work_shift_id:
            return Response({"detail": "Le champ work_shift est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            work_shift = WorkShift.objects.get(id=work_shift_id)
        except WorkShift.DoesNotExist:
            return Response({"detail": "Quart de travail introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if work_shift.tenant_id != employee.tenant_id:
            return Response(
                {"detail": "Le quart de travail doit appartenir au meme tenant que l'employee."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        self._upsert_employee_assignment(employee, work_shift=work_shift)
        employee.work_shift = work_shift
        employee.needs_gateway_push = True
        employee.last_gateway_push_at = None
        employee.save(update_fields=["work_shift", "needs_gateway_push", "last_gateway_push_at", "updated_at"])
        employee.work_shifts.add(work_shift)
        response_payload = dict(self.get_serializer(employee).data)
        return self._response_with_auto_sync(request, employee, response_payload)

    @action(detail=True, methods=["post"], url_path="assign-work-shifts")
    def assign_work_shifts(self, request, pk=None):
        employee = self.get_object()
        work_shift_ids = request.data.get("work_shifts")
        replace = self._to_bool(request.data.get("replace"), default=True)

        if not isinstance(work_shift_ids, list) or not work_shift_ids:
            return Response(
                {"detail": "Le champ work_shifts est obligatoire et doit etre une liste non vide."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        work_shifts = list(WorkShift.objects.filter(id__in=work_shift_ids).order_by("id"))
        found_ids = {shift.id for shift in work_shifts}
        missing_ids = [shift_id for shift_id in work_shift_ids if shift_id not in found_ids]
        if missing_ids:
            return Response(
                {"detail": f"Quarts de travail introuvables: {missing_ids}."},
                status=status.HTTP_404_NOT_FOUND,
            )

        invalid_ids = [shift.id for shift in work_shifts if shift.tenant_id != employee.tenant_id]
        if invalid_ids:
            return Response(
                {"detail": f"Les quarts {invalid_ids} doivent appartenir au meme tenant que l'employee."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if replace:
            employee.work_shifts.set(work_shifts)
        else:
            employee.work_shifts.add(*work_shifts)

        self._upsert_employee_assignment(employee, work_shift=work_shifts[0])
        employee.work_shift = work_shifts[0]
        employee.needs_gateway_push = True
        employee.last_gateway_push_at = None
        employee.save(update_fields=["work_shift", "needs_gateway_push", "last_gateway_push_at", "updated_at"])
        response_payload = dict(self.get_serializer(employee).data)
        return self._response_with_auto_sync(request, employee, response_payload)

    @action(detail=False, methods=["post"], url_path="push-pending")
    def push_pending(self, request):
        tenant_id = request.data.get("tenant")
        if not tenant_id:
            return Response({"detail": "Le champ tenant est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist:
            return Response({"detail": "Tenant introuvable."}, status=status.HTTP_404_NOT_FOUND)
        try:
            _require_tenant_scope(request, tenant)
        except PermissionDenied as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        employee_ids = request.data.get("employee_ids")
        if employee_ids is not None and not isinstance(employee_ids, list):
            return Response({"detail": "employee_ids doit etre une liste."}, status=status.HTTP_400_BAD_REQUEST)

        dev_indexes_input = request.data.get("dev_indexes")
        if dev_indexes_input is not None and not isinstance(dev_indexes_input, list):
            return Response({"detail": "dev_indexes doit etre une liste."}, status=status.HTTP_400_BAD_REQUEST)

        queryset = (
            Employee.objects.filter(tenant=tenant, needs_gateway_push=True)
            .prefetch_related("devices", "department__devices", "cards", "fingerprints", "attributes", "access_groups__readers")
            .order_by("updated_at", "id")
        )
        if employee_ids:
            queryset = queryset.filter(id__in=employee_ids)

        employees = list(queryset)
        pushed = []
        errors = []
        pushed_count = 0

        for employee in employees:
            result = self._push_employee(employee, dev_indexes=dev_indexes_input)
            if result.get("status") == "ok":
                self._mark_gateway_push_success(employee)
                pushed_count += 1
            elif result.get("status") == "skipped":
                errors.append(
                    {
                        "employee_id": employee.id,
                        "employee_no": employee.employee_no,
                        "detail": result.get("detail", "Aucun device cible."),
                    }
                )
            else:
                for err in result.get("errors", []):
                    errors.append(
                        {
                            "employee_id": employee.id,
                            "employee_no": employee.employee_no,
                            "detail": err.get("detail", "Erreur gateway"),
                            "dev_index": err.get("dev_index", ""),
                        }
                    )
            pushed.append(result)

        output_status = status.HTTP_200_OK if not errors else status.HTTP_207_MULTI_STATUS
        return Response(
            {
                "status": "ok" if not errors else "partial",
                "tenant": tenant.id,
                "pending_count": len(employees),
                "pushed_count": pushed_count,
                "results": pushed,
                "errors": errors,
            },
            status=output_status,
        )

    @action(detail=False, methods=["post"], url_path="import-from-gateway")
    def import_from_gateway(self, request):
        tenant_id = request.data.get("tenant")
        if not tenant_id:
            return Response({"detail": "Le champ tenant est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist:
            return Response({"detail": "Tenant introuvable."}, status=status.HTTP_404_NOT_FOUND)
        try:
            _require_tenant_scope(request, tenant)
        except PermissionDenied as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        link_device = self._to_bool(request.data.get("link_device", True), default=True)
        max_results = int(request.data.get("max_results", 50))
        include_fingerprints = self._to_bool(request.data.get("include_fingerprints", True), default=True)

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

                card_rows = []
                card_lookup_error = None
                try:
                    card_payload = client.search_access_cards_all(dev_index=dev_index, max_results=max_results)
                    card_search = card_payload.get("CardInfoSearch", {}) if isinstance(card_payload, dict) else {}
                    card_rows = card_search.get("CardInfo", []) if isinstance(card_search, dict) else []
                    if isinstance(card_rows, dict):
                        card_rows = [card_rows]
                    if not isinstance(card_rows, list):
                        card_rows = []
                except Exception as exc:  # noqa: BLE001
                    card_lookup_error = str(exc)
                    card_rows = []

                card_map: dict[str, list[dict]] = {}
                for card_row in card_rows:
                    if not isinstance(card_row, dict):
                        continue
                    card_employee_no = str(
                        card_row.get("employeeNo")
                        or card_row.get("employeeNoString")
                        or card_row.get("cardUserNo")
                        or ""
                    ).strip()
                    if not card_employee_no:
                        continue
                    card_map.setdefault(card_employee_no, []).append(card_row)

                fingerprint_map: dict[str, list[dict]] = {}
                fingerprint_lookup_errors: dict[str, str] = {}
                if include_fingerprints:
                    for row in users:
                        if not isinstance(row, dict):
                            continue
                        employee_no = str(row.get("employeeNo") or "").strip()
                        if not employee_no:
                            continue
                        try:
                            fp_payload = client.search_access_fingerprints_all(
                                dev_index=dev_index,
                                employee_no=employee_no,
                            )
                            fp_info = fp_payload.get("FingerPrintInfo", {}) if isinstance(fp_payload, dict) else {}
                            fp_rows = fp_info.get("FingerPrintList", []) if isinstance(fp_info, dict) else []
                            if isinstance(fp_rows, dict):
                                fp_rows = [fp_rows]
                            if not isinstance(fp_rows, list):
                                fp_rows = []
                            fingerprint_map[employee_no] = [item for item in fp_rows if isinstance(item, dict)]
                        except Exception as exc:  # noqa: BLE001
                            fingerprint_lookup_errors[employee_no] = str(exc)

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
                    is_active = self._to_bool(valid.get("enable", True), default=True)
                    user_type = str(row.get("userType") or "").strip().lower()
                    is_visitor = user_type == "visitor"
                    is_super_user = self._to_bool(
                        row.get("isSuperUser", row.get("superUser", False)),
                        default=False,
                    )
                    is_blocklisted = self._to_bool(
                        row.get("isBlocklisted", row.get("isBlocked", False)),
                        default=False,
                    )
                    is_device_operator = self._to_bool(row.get("isDeviceOperator", False), default=False)

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
                            "remark": str(row.get("remark") or "").strip(),
                            "valid_from": valid_from,
                            "valid_to": valid_to,
                            "is_active": is_active,
                            "access_group": str(row.get("belongGroup") or "").strip(),
                            "pin_code": str(row.get("password") or "").strip(),
                            "is_super_user": is_super_user,
                            "only_authenticate": self._to_bool(row.get("onlyVerify", False), default=False),
                            "extended_door_open_time": self._to_int_or_none(row.get("maxOpenDoorTime")),
                            "is_blocklisted": is_blocklisted,
                            "is_visitor": is_visitor,
                            "is_device_operator": is_device_operator,
                            "custom_profile": str(row.get("customProfile") or "").strip(),
                            "date_of_birth": self._parse_gateway_date(row.get("dateOfBirth")),
                            "identity_type": str(row.get("certificateType") or row.get("identityType") or "").strip(),
                            "identity_no": str(row.get("certificateNo") or row.get("identityNo") or "").strip(),
                            "position": str(row.get("position") or "").strip(),
                            "hire_date": self._parse_gateway_date(row.get("hireDate")),
                            "address": str(row.get("address") or "").strip(),
                            "needs_gateway_push": False,
                            "last_gateway_push_at": timezone.now(),
                        },
                    )
                    if was_created:
                        created_count += 1
                    else:
                        updated_count += 1
                    imported_count += 1

                    self._sync_gateway_attributes(employee, row)

                    employee_card_rows = card_map.get(employee_no, [])
                    card_numbers: list[str] = []
                    for card_row in employee_card_rows:
                        card_no = str(card_row.get("cardNo") or "").strip()
                        if not card_no:
                            continue
                        card_type = str(card_row.get("cardType") or "normalCard").strip() or "normalCard"
                        EmployeeCard.objects.update_or_create(
                            employee=employee,
                            card_no=card_no,
                            defaults={"card_type": card_type},
                        )
                        card_numbers.append(card_no)

                    employee_fingerprints = fingerprint_map.get(employee_no, [])
                    fingerprint_slots: list[int] = []
                    seen_finger_indexes: set[int] = set()
                    for fingerprint_row in employee_fingerprints:
                        finger_index = self._to_int_or_none(fingerprint_row.get("fingerPrintID"))
                        if finger_index is None or not (1 <= finger_index <= 10) or finger_index in seen_finger_indexes:
                            continue
                        finger_data = str(fingerprint_row.get("fingerData") or "").strip()
                        if not finger_data:
                            continue
                        seen_finger_indexes.add(finger_index)
                        EmployeeFingerprint.objects.update_or_create(
                            employee=employee,
                            finger_index=finger_index,
                            defaults={"template": finger_data},
                        )
                        fingerprint_slots.append(finger_index)

                    if link_device and dev_index in device_by_index:
                        employee.devices.add(device_by_index[dev_index])

                    imported_row = {
                        "employee_id": employee.id,
                        "employee_no": employee.employee_no,
                        "name": employee.name,
                        "dev_index": dev_index,
                        "created": was_created,
                        "gateway_user_info": row,
                        "card_numbers": card_numbers,
                        "fingerprint_slots": sorted(fingerprint_slots),
                    }
                    if card_lookup_error:
                        imported_row["card_lookup_error"] = card_lookup_error
                    if employee_no in fingerprint_lookup_errors:
                        imported_row["fingerprint_lookup_error"] = fingerprint_lookup_errors[employee_no]
                    imported.append(imported_row)
            except Exception as exc:  # noqa: BLE001
                errors.append({"dev_index": dev_index, "detail": str(exc)})

        response_status = status.HTTP_200_OK if not errors else status.HTTP_207_MULTI_STATUS
        return Response(
            {
                "status": "ok" if not errors else "partial",
                "tenant": tenant.id,
                "dev_indexes": dev_indexes,
                "include_fingerprints": include_fingerprints,
                "imported_count": imported_count,
                "created_count": created_count,
                "updated_count": updated_count,
                "imported": imported,
                "errors": errors,
            },
            status=response_status,
        )


class LeaveRequestViewSet(viewsets.ModelViewSet):
    queryset = LeaveRequest.objects.select_related("tenant", "employee", "approved_by").order_by("-id")
    serializer_class = LeaveRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = _scope_to_request_tenants(super().get_queryset(), self.request, tenant_field="tenant_id")
        tenant_code = str(self.request.query_params.get("tenant") or "").strip()
        if tenant_code:
            queryset = queryset.filter(tenant__code__iexact=tenant_code)
        employee_id = str(self.request.query_params.get("employee") or "").strip()
        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
        status_value = str(self.request.query_params.get("status") or "").strip().lower()
        if status_value:
            queryset = queryset.filter(status=status_value)
        start_from = parse_date(str(self.request.query_params.get("start_from") or "").strip())
        end_to = parse_date(str(self.request.query_params.get("end_to") or "").strip())
        if start_from:
            queryset = queryset.filter(end_date__gte=start_from)
        if end_to:
            queryset = queryset.filter(start_date__lte=end_to)
        return queryset

    def perform_create(self, serializer):
        tenant = serializer.validated_data.get("tenant")
        _require_tenant_scope(self.request, tenant)
        serializer.save()

    def perform_update(self, serializer):
        instance = serializer.instance
        tenant = serializer.validated_data.get("tenant", instance.tenant)
        _require_tenant_scope(self.request, tenant)
        if serializer.validated_data.get("tenant") is not None and tenant.id != instance.tenant_id:
            raise PermissionDenied("Changing tenant is not allowed for this resource.")
        serializer.save()
