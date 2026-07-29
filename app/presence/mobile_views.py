"""Surface API de l'application mobile employé (/api/mobile/*).

Seuls comptes liés à une fiche Employee active (via get_employee_tenant_ids —
le rôle employee n'accède à rien d'autre). Les administrateurs testent en
liant leur propre compte à une fiche employé : pas de contournement spécial.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from django.utils import timezone as dj_timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from employees.models import Employee
from employees.schedule_resolver import ScheduleResolver
from hik_gateway.models import AttendanceLog
from presence.models import Site
from presence.punch_engine import (
    PunchAttempt,
    PunchContext,
    SitePoint,
    evaluate_mobile_punch,
    suggested_action,
)
from presence.services import record_mobile_punch


class MobilePunchThrottle(ScopedRateThrottle):
    scope = "mobile_punch"


DAY_START_LOCAL = time(3, 0)  # journée de pointage : à partir de 03:00 locale


def _get_linked_employee(request) -> Employee | None:
    return (
        Employee.objects.select_related("tenant", "planning", "work_shift", "department")
        .filter(user=request.user, is_active=True)
        .first()
    )


def _profile_not_linked() -> Response:
    return Response(
        {"code": "PROFILE_NOT_LINKED", "detail": "Aucune fiche employé active liée à ce compte."},
        status=status.HTTP_403_FORBIDDEN,
    )


def _day_window_start(tz, local_now: datetime) -> datetime:
    day_start = datetime.combine(local_now.date(), DAY_START_LOCAL, tzinfo=tz)
    if local_now < day_start:
        day_start -= timedelta(days=1)
    return day_start


def _punches_today(employee: Employee, tz, local_now: datetime):
    from django.db.models import Q

    window_start = _day_window_start(tz, local_now)
    return list(
        AttendanceLog.objects.filter(
            tenant=employee.tenant,
            timestamp__gte=window_start,
            normalized_action__in=[AttendanceLog.ACTION_CHECK_IN, AttendanceLog.ACTION_CHECK_OUT],
        )
        .filter(Q(employee=employee) | Q(person_id=employee.employee_no))
        .select_related("device")
        .order_by("timestamp")
    )


def _serialize_time(value) -> str | None:
    return value.strftime("%H:%M") if value is not None else None


def _serialize_day_schedule(schedule: dict) -> dict:
    return {
        "is_rest_day": schedule.get("is_rest_day", False),
        "has_work_period": schedule.get("has_work_period", False),
        "slots": [
            {
                "label": slot.get("label"),
                "slot_type": slot.get("slot_type"),
                "start_time": _serialize_time(slot.get("start_time")),
                "end_time": _serialize_time(slot.get("end_time")),
            }
            for slot in schedule.get("slots", [])
        ],
    }


def _serialize_punch(log: AttendanceLog) -> dict:
    site_name = None
    if log.raw_event_id and isinstance(log.raw_event.payload, dict):
        site_name = log.raw_event.payload.get("site_name")
    return {
        "id": log.id,
        "timestamp": log.timestamp.isoformat(),
        "action": log.normalized_action,
        "source": log.source,
        "site_name": site_name or (log.device.device_name if log.device_id else None),
    }


def _active_sites(employee: Employee) -> list[Site]:
    return list(Site.objects.filter(tenant=employee.tenant, is_active=True).order_by("name"))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mobile_me_api(request):
    employee = _get_linked_employee(request)
    if employee is None:
        return _profile_not_linked()

    resolver = ScheduleResolver()
    tz = resolver.resolve_employee_timezone(employee)
    local_now = dj_timezone.now().astimezone(tz)
    schedule = resolver.build_day_schedule(employee, local_now.date())
    punches = _punches_today(employee, tz, local_now)
    last_action = punches[-1].normalized_action if punches else None

    return Response(
        {
            "employee": {
                "id": employee.id,
                "employee_no": employee.employee_no,
                "name": employee.name,
                "tenant": {
                    "id": employee.tenant_id,
                    "code": employee.tenant.code,
                    "name": employee.tenant.name,
                },
            },
            "date": local_now.date().isoformat(),
            "timezone": str(tz),
            "day_schedule": _serialize_day_schedule(schedule),
            "punches_today": [
                _serialize_punch(log)
                for log in AttendanceLog.objects.filter(id__in=[p.id for p in punches])
                .select_related("device", "raw_event")
                .order_by("timestamp")
            ],
            "suggested_action": suggested_action(last_action),
            "has_punched_in": any(
                p.normalized_action == AttendanceLog.ACTION_CHECK_IN for p in punches
            ),
            "sites": [
                {
                    "id": site.id,
                    "name": site.name,
                    "latitude": float(site.latitude),
                    "longitude": float(site.longitude),
                    "radius_m": site.radius_m,
                }
                for site in _active_sites(employee)
            ],
        }
    )


def _decision_error_response(decision) -> Response:
    body: dict = {"code": decision.error_code}
    http = {
        "INVALID_COORDINATES": status.HTTP_400_BAD_REQUEST,
        "ACCURACY_TOO_LOW": status.HTTP_400_BAD_REQUEST,
        "NO_SITE_CONFIGURED": status.HTTP_409_CONFLICT,
        "OUT_OF_ZONE": status.HTTP_403_FORBIDDEN,
        "TOO_SOON": status.HTTP_429_TOO_MANY_REQUESTS,
        "SUGGESTED_ACTION_CHANGED": status.HTTP_409_CONFLICT,
    }[decision.error_code]
    if decision.error_code == "OUT_OF_ZONE":
        body.update(
            {
                "detail": "Vous êtes hors zone de pointage.",
                "nearest_site": {"id": decision.nearest_site.id, "name": decision.nearest_site.name},
                "distance_m": decision.distance_m,
                "tolerance_m": decision.tolerance_m,
            }
        )
    elif decision.error_code == "TOO_SOON":
        body.update({"detail": "Pointage trop rapproché du précédent.", "retry_after_s": decision.retry_after_s})
    elif decision.error_code == "SUGGESTED_ACTION_CHANGED":
        body.update(
            {"detail": "L'action suggérée a changé.", "suggested_action": decision.suggested_action}
        )
    elif decision.error_code == "ACCURACY_TOO_LOW":
        body.update({"detail": "Précision GPS insuffisante.", **decision.extra})
    elif decision.error_code == "NO_SITE_CONFIGURED":
        body["detail"] = "Aucun site de pointage actif n'est configuré."
    else:
        body["detail"] = "Coordonnées invalides."
    return Response(body, status=http)


def _success_payload(log: AttendanceLog, decision_zone: str | None, employee: Employee) -> dict:
    payload = log.raw_event.payload if isinstance(log.raw_event.payload, dict) else {}
    resolver = ScheduleResolver()
    match = resolver.resolve_shift_from_timestamp(
        employee, log.timestamp, direction_hint=log.direction
    )
    delta_minutes = None
    in_schedule = match is not None
    if match is not None and match.work_shift is not None:
        shift_start = match.work_shift.start_time
        if shift_start is not None and log.normalized_action == AttendanceLog.ACTION_CHECK_IN:
            tz = resolver.resolve_employee_timezone(employee)
            local_ts = log.timestamp.astimezone(tz)
            expected = datetime.combine(match.shift_date, shift_start, tzinfo=tz)
            delta_minutes = round((local_ts - expected).total_seconds() / 60)
    return {
        "status": "ok",
        "action": log.normalized_action,
        "timestamp": log.timestamp.isoformat(),
        "site": {"id": payload.get("site_id"), "name": payload.get("site_name")},
        "distance_m": payload.get("distance_m"),
        "zone": decision_zone or payload.get("zone"),
        "schedule": {"in_schedule": in_schedule, "delta_minutes": delta_minutes},
    }


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([MobilePunchThrottle])
def mobile_punch_api(request):
    employee = _get_linked_employee(request)
    if employee is None:
        return _profile_not_linked()

    data = request.data
    idempotency_key = str(data.get("idempotency_key") or "").strip()
    if not idempotency_key or len(idempotency_key) > 64:
        return Response(
            {"code": "MISSING_IDEMPOTENCY_KEY", "detail": "idempotency_key est requis (≤ 64 caractères)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Retry réseau : même clé → même réponse de succès, sans réévaluation.
    from hik_gateway.models import RawEvent

    dedupe_key = f"mobile:{employee.tenant_id}:{employee.id}:{idempotency_key}"
    existing = (
        RawEvent.objects.filter(dedupe_key=dedupe_key).select_related("attendance_log").first()
    )
    if existing is not None and hasattr(existing, "attendance_log"):
        return Response(
            _success_payload(existing.attendance_log, None, employee), status=status.HTTP_200_OK
        )

    try:
        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))
        accuracy_m = float(data.get("accuracy_m"))
    except (TypeError, ValueError):
        return Response(
            {"code": "INVALID_COORDINATES", "detail": "latitude, longitude et accuracy_m sont requis."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    action = str(data.get("action") or "").strip() or None
    if action is not None and action not in {"CHECK_IN", "CHECK_OUT"}:
        return Response(
            {"code": "INVALID_ACTION", "detail": "action doit valoir CHECK_IN ou CHECK_OUT."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    from django.conf import settings as dj_settings

    resolver = ScheduleResolver()
    tz = resolver.resolve_employee_timezone(employee)
    server_now = dj_timezone.now()
    local_now = server_now.astimezone(tz)
    punches = _punches_today(employee, tz, local_now)
    last = punches[-1] if punches else None

    context = PunchContext(
        server_now=server_now,
        sites=[
            SitePoint(
                id=site.id,
                name=site.name,
                latitude=float(site.latitude),
                longitude=float(site.longitude),
                radius_m=site.radius_m,
            )
            for site in _active_sites(employee)
        ],
        last_punch_action=last.normalized_action if last else None,
        last_punch_at=last.timestamp if last else None,
        max_accuracy_m=float(getattr(dj_settings, "MOBILE_PUNCH_MAX_ACCURACY_M", 150)),
        borderline_grace_m=float(getattr(dj_settings, "MOBILE_PUNCH_BORDERLINE_GRACE_M", 20)),
        borderline_max_accuracy_m=float(
            getattr(dj_settings, "MOBILE_PUNCH_BORDERLINE_MAX_ACCURACY_M", 50)
        ),
        min_interval_seconds=int(getattr(dj_settings, "MOBILE_PUNCH_MIN_INTERVAL_SECONDS", 60)),
    )
    attempt = PunchAttempt(latitude=latitude, longitude=longitude, accuracy_m=accuracy_m, action=action)
    decision = evaluate_mobile_punch(attempt, context)

    if decision.verdict != "accepted":
        return _decision_error_response(decision)

    client_reported_at = parse_datetime(str(data.get("client_reported_at") or "")) or None
    log, created = record_mobile_punch(
        employee=employee,
        decision=decision,
        attempt=attempt,
        idempotency_key=idempotency_key,
        client_reported_at=client_reported_at,
        app_version=str(data.get("app_version") or "")[:64],
        mocked=data.get("mocked"),
    )
    return Response(
        _success_payload(log, decision.zone, employee),
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mobile_history_api(request):
    employee = _get_linked_employee(request)
    if employee is None:
        return _profile_not_linked()

    from django.db.models import Q

    try:
        limit = min(100, max(1, int(request.query_params.get("limit") or 50)))
    except (TypeError, ValueError):
        limit = 50

    logs = (
        AttendanceLog.objects.filter(
            tenant=employee.tenant,
            normalized_action__in=[AttendanceLog.ACTION_CHECK_IN, AttendanceLog.ACTION_CHECK_OUT],
        )
        .filter(Q(employee=employee) | Q(person_id=employee.employee_no))
        .select_related("device", "raw_event")
        .order_by("-timestamp")[:limit]
    )
    results = [_serialize_punch(log) for log in logs]
    return Response({"count": len(results), "results": results})
