from __future__ import annotations

import hashlib
from datetime import datetime, timezone as dt_timezone

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from employees.models import Employee, EmployeeCard
from hik_gateway.models import AttendanceLog, Device, DeviceReaderConfig, RawEvent
from hik_gateway.services.device_sync import sync_gateway_devices
from tenants.models import Tenant

ATTENDANCE_DIRECTION_MAP = {
    "checkin": "IN",
    "breakin": "IN",
    "overtimein": "IN",
    "checkout": "OUT",
    "breakout": "OUT",
    "overtimeout": "OUT",
}
ATTENDANCE_ACTION_MAP = {
    "checkin": AttendanceLog.ACTION_CHECK_IN,
    "checkout": AttendanceLog.ACTION_CHECK_OUT,
    "breakin": AttendanceLog.ACTION_BREAK_IN,
    "breakout": AttendanceLog.ACTION_BREAK_OUT,
    "overtimein": AttendanceLog.ACTION_OVERTIME_IN,
    "overtimeout": AttendanceLog.ACTION_OVERTIME_OUT,
}
DENIED_STATUS_TOKENS = ("deny", "denied", "refus", "failed", "forbid", "unauthor")

AUTH_SUCCESS_SUB_TYPES = {1, 2, 15, 16, 38, 40, 43, 46}
NON_DIRECTIONAL_SUB_TYPES = {3, 6, 25, 26, 27, 28}
CONNECTED_DEVICE_STATUSES = ("online", "active", "connected")


def _as_aware(dt: datetime | None) -> datetime:
    if dt is None:
        return timezone.now()
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, dt_timezone.utc)
    return dt


def _event_root(payload: dict) -> dict:
    if "EventNotificationAlert" in payload:
        return payload["EventNotificationAlert"]
    return payload


def _to_int(value):
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _build_dedupe_key(
    tenant_id: int | None,
    dev_index: str,
    event_datetime: str,
    person_hint: str,
    serial_no: str,
) -> str:
    raw = "|".join(
        [
            str(tenant_id or ""),
            dev_index or "",
            event_datetime or "",
            person_hint or "",
            serial_no or "",
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _person_hint(access_event: dict) -> str:
    return str(
        access_event.get("employeeNoString")
        or access_event.get("employeeNo")
        or access_event.get("cardNo")
        or ""
    )


def _attendance_status_value(access_event: dict) -> str:
    return str(access_event.get("attendanceStatus") or "").strip()


def _resolve_employee(device: Device, access_event: dict) -> tuple[Employee | None, str]:
    employee_no_string = str(access_event.get("employeeNoString") or "").strip()
    employee_no = str(access_event.get("employeeNo") or "").strip()
    card_no = str(access_event.get("cardNo") or "").strip()

    employee = None
    if employee_no_string:
        employee = Employee.objects.filter(tenant=device.tenant, employee_no=employee_no_string).first()
    if employee is None and employee_no:
        employee = Employee.objects.filter(tenant=device.tenant, employee_no=employee_no).first()
    if employee is None and card_no:
        card = (
            EmployeeCard.objects.select_related("employee")
            .filter(employee__tenant=device.tenant, card_no=card_no)
            .first()
        )
        if card:
            employee = card.employee

    if employee:
        return employee, employee.employee_no
    return None, _person_hint(access_event)


def _resolve_direction(device: Device | None, access_event: dict) -> tuple[str, bool]:
    status = _attendance_status_value(access_event)
    normalized = status.lower()
    if normalized and normalized != "undefined":
        return ATTENDANCE_DIRECTION_MAP.get(normalized, "UNKNOWN"), True

    sub_event_type = _to_int(access_event.get("subEventType"))
    if sub_event_type in NON_DIRECTIONAL_SUB_TYPES:
        return "UNKNOWN", False
    if sub_event_type == 23:
        return "OUT", False
    if sub_event_type in AUTH_SUCCESS_SUB_TYPES:
        door_no = _to_int(access_event.get("doorNo"))
        card_reader_no = _to_int(access_event.get("cardReaderNo"))
        if device is not None and door_no is not None and card_reader_no is not None:
            reader_config = DeviceReaderConfig.objects.filter(
                device=device,
                door_no=door_no,
                card_reader_no=card_reader_no,
            ).first()
            if reader_config:
                return reader_config.direction_default, False
        return "IN", False

    return "UNKNOWN", False


def _resolve_normalized_action(access_event: dict, direction: str) -> str:
    status = _attendance_status_value(access_event)
    normalized = status.lower()
    if any(token in normalized for token in DENIED_STATUS_TOKENS):
        return AttendanceLog.ACTION_ACCESS_DENIED

    if normalized and normalized != "undefined":
        return ATTENDANCE_ACTION_MAP.get(normalized, AttendanceLog.ACTION_UNKNOWN)

    if direction == "IN":
        return AttendanceLog.ACTION_CHECK_IN
    if direction == "OUT":
        return AttendanceLog.ACTION_CHECK_OUT
    return AttendanceLog.ACTION_UNKNOWN


def _connected_status_filter() -> Q:
    connected_filter = Q(status__iexact=CONNECTED_DEVICE_STATUSES[0])
    for status_value in CONNECTED_DEVICE_STATUSES[1:]:
        connected_filter |= Q(status__iexact=status_value)
    return connected_filter


def _get_or_resync_device(dev_index: str, tenant: Tenant | None = None) -> Device | None:
    queryset = Device.objects.filter(dev_index=dev_index)
    if tenant is not None:
        queryset = queryset.filter(tenant=tenant)

    device = queryset.filter(_connected_status_filter()).first()
    if device:
        return device

    if tenant is not None:
        sync_gateway_devices(tenant)
        device = Device.objects.filter(tenant=tenant, dev_index=dev_index).filter(_connected_status_filter()).first()
        if device:
            return device

    return queryset.first()


def ingest_event(payload: dict, source: str, tenant: Tenant | None = None) -> tuple[RawEvent | None, AttendanceLog | None]:
    root = _event_root(payload)
    if root.get("eventType") != "AccessControllerEvent":
        return None, None

    access_event = root.get("AccessControllerEvent", {})
    dev_index = root.get("devIndex", "")
    if not dev_index:
        return None, None

    device = _get_or_resync_device(dev_index, tenant=tenant)
    tenant_for_event = device.tenant if device else tenant
    if not tenant_for_event:
        return None, None

    timestamp_raw = root.get("dateTime") or access_event.get("time")
    event_dt = _as_aware(parse_datetime(timestamp_raw or ""))
    person_hint = _person_hint(access_event)
    serial_no = str(access_event.get("serialNo") or root.get("serialNo") or "")
    resolved_employee = None
    resolved_person_id = person_hint
    if device is not None:
        resolved_employee, resolved_person_id = _resolve_employee(device, access_event)

    dedupe_key = _build_dedupe_key(tenant_for_event.id, dev_index, timestamp_raw or "", person_hint, serial_no)
    event_type = root.get("eventType", "")
    attendance_status = _attendance_status_value(access_event)
    direction, from_status = _resolve_direction(device, access_event)
    normalized_action = _resolve_normalized_action(access_event, direction)

    try:
        with transaction.atomic():
            raw_event = RawEvent.objects.create(
                tenant=tenant_for_event,
                device=device,
                dev_index=dev_index,
                event_type=event_type,
                event_datetime=event_dt,
                major_event_type=_to_int(access_event.get("majorEventType")),
                sub_event_type=_to_int(access_event.get("subEventType")),
                serial_no=_to_int(access_event.get("serialNo") or root.get("serialNo")),
                front_serial_no=_to_int(access_event.get("frontSerialNo") or root.get("frontSerialNo")),
                employee_no=str(access_event.get("employeeNo") or ""),
                employee_no_string=str(access_event.get("employeeNoString") or ""),
                card_no=str(access_event.get("cardNo") or ""),
                card_reader_no=_to_int(access_event.get("cardReaderNo")),
                door_no=_to_int(access_event.get("doorNo")),
                attendance_status=attendance_status,
                dedupe_key=dedupe_key,
                payload=payload,
            )

            if device is None:
                return raw_event, None

            attendance = AttendanceLog.objects.create(
                tenant=tenant_for_event,
                employee=resolved_employee,
                person_id=resolved_person_id,
                device=device,
                timestamp=event_dt,
                attendance_type=attendance_status or ("fallback" if not from_status else "unknown"),
                attendance_status=attendance_status,
                normalized_action=normalized_action,
                direction=direction,
                source=source,
                raw_event=raw_event,
            )
        return raw_event, attendance
    except IntegrityError:
        raw_event = RawEvent.objects.filter(dedupe_key=dedupe_key).first()
        if raw_event:
            attendance = AttendanceLog.objects.filter(raw_event=raw_event).first()
            return raw_event, attendance
        return None, None


def ingest_acs_event(device: Device, acs_event: dict) -> tuple[RawEvent | None, AttendanceLog | None]:
    normalized_acs_event = dict(acs_event)
    if "majorEventType" not in normalized_acs_event and normalized_acs_event.get("major") is not None:
        normalized_acs_event["majorEventType"] = normalized_acs_event.get("major")
    if "subEventType" not in normalized_acs_event and normalized_acs_event.get("minor") is not None:
        normalized_acs_event["subEventType"] = normalized_acs_event.get("minor")

    wrapped = {
        "EventNotificationAlert": {
            "eventType": "AccessControllerEvent",
            "devIndex": device.dev_index,
            "dateTime": acs_event.get("dateTime") or acs_event.get("time"),
            "AccessControllerEvent": normalized_acs_event,
        }
    }
    return ingest_event(wrapped, source=AttendanceLog.SOURCE_CATCHUP)
