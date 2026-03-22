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
ACCESS_EVENT_TYPE_ALIASES = {"accesscontrollerevent", "acsevent"}
ACCESS_EVENT_CONTAINER_KEYS = (
    "AccessControllerEvent",
    "AcsEvent",
    "AcsEventInfo",
    "acsEvent",
    "accessControllerEvent",
)


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


def _coalesce(*values):
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                continue
            return stripped
        return value
    return None


def _event_value(event: dict, *keys: str):
    if not isinstance(event, dict):
        return None
    for key in keys:
        if key not in event:
            continue
        value = event.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _normalize_event_type(value: str | None) -> str:
    normalized = str(value or "").strip()
    if normalized.lower() in ACCESS_EVENT_TYPE_ALIASES:
        return "AccessControllerEvent"
    return normalized


def _looks_like_access_event(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    marker_keys = (
        "majorEventType",
        "major",
        "subEventType",
        "minor",
        "serialNo",
        "serial_no",
        "employeeNoString",
        "employeeNo",
        "cardNo",
        "card_no",
        "cardNumber",
        "time",
        "dateTime",
        "eventTime",
        "doorNo",
        "cardReaderNo",
    )
    return any(key in payload for key in marker_keys)


def _extract_access_event(root: dict) -> dict:
    if not isinstance(root, dict):
        return {}

    for key in ACCESS_EVENT_CONTAINER_KEYS:
        candidate = root.get(key)
        if isinstance(candidate, dict):
            return candidate

    if _looks_like_access_event(root):
        return root
    return {}


def _normalize_access_event(access_event: dict, root: dict) -> dict:
    normalized = dict(access_event or {})

    employee_no = _coalesce(
        _event_value(access_event, "employeeNo", "employee_no"),
        _event_value(access_event, "employeeNoString", "employee_no_string"),
    )
    if employee_no is not None:
        normalized["employeeNo"] = str(employee_no).strip()

    employee_no_string = _coalesce(
        _event_value(access_event, "employeeNoString", "employee_no_string"),
        _event_value(access_event, "employeeNo", "employee_no"),
    )
    if employee_no_string is not None:
        normalized["employeeNoString"] = str(employee_no_string).strip()

    card_no = _coalesce(_event_value(access_event, "cardNo", "card_no", "cardNumber"))
    if card_no is not None:
        normalized["cardNo"] = str(card_no).strip()

    serial_no = _coalesce(
        _event_value(access_event, "serialNo", "serial_no"),
        _event_value(root, "serialNo", "serial_no"),
    )
    if serial_no is not None:
        normalized["serialNo"] = serial_no

    front_serial_no = _coalesce(
        _event_value(access_event, "frontSerialNo", "front_serial_no"),
        _event_value(root, "frontSerialNo", "front_serial_no"),
    )
    if front_serial_no is not None:
        normalized["frontSerialNo"] = front_serial_no

    major_type = _coalesce(
        _event_value(access_event, "majorEventType", "major_event_type"),
        _event_value(access_event, "major"),
        _event_value(root, "majorEventType", "major"),
    )
    if major_type is not None:
        normalized["majorEventType"] = major_type

    sub_type = _coalesce(
        _event_value(access_event, "subEventType", "sub_event_type"),
        _event_value(access_event, "minor"),
        _event_value(root, "subEventType", "minor"),
    )
    if sub_type is not None:
        normalized["subEventType"] = sub_type

    event_time = _coalesce(
        _event_value(root, "dateTime", "time", "eventTime"),
        _event_value(access_event, "dateTime", "time", "eventTime", "event_time"),
    )
    if event_time is not None:
        normalized["dateTime"] = event_time
        normalized.setdefault("time", event_time)

    door_no = _coalesce(_event_value(access_event, "doorNo", "door_no"))
    if door_no is not None:
        normalized["doorNo"] = door_no

    card_reader_no = _coalesce(_event_value(access_event, "cardReaderNo", "card_reader_no"))
    if card_reader_no is not None:
        normalized["cardReaderNo"] = card_reader_no

    attendance_status = _coalesce(
        _event_value(access_event, "attendanceStatus", "attendance_status"),
        _event_value(access_event, "status"),
    )
    if attendance_status is not None:
        normalized["attendanceStatus"] = str(attendance_status).strip()

    return normalized


def _find_device_by_identifier(identifier: str, tenant: Tenant | None = None) -> Device | None:
    normalized = str(identifier or "").strip()
    if not normalized:
        return None

    queryset = Device.objects.filter(
        Q(dev_index__iexact=normalized)
        | Q(device_id__iexact=normalized)
        | Q(serial_number__iexact=normalized)
    )
    if tenant is not None:
        queryset = queryset.filter(tenant=tenant)

    connected_device = queryset.filter(_connected_status_filter()).order_by("id").first()
    if connected_device:
        return connected_device

    if tenant is None:
        matches = list(queryset.order_by("id")[:2])
        if len(matches) == 1:
            return matches[0]
        return None

    return queryset.order_by("id").first()


def _resolve_device_from_payload(
    root: dict,
    access_event: dict,
    *,
    tenant: Tenant | None = None,
) -> tuple[Device | None, str]:
    dev_index_value = _coalesce(
        _event_value(root, "devIndex", "dev_index", "devIndexCode"),
        _event_value(access_event, "devIndex", "dev_index", "devIndexCode"),
    )
    dev_index = str(dev_index_value or "").strip()
    if dev_index:
        return _get_or_resync_device(dev_index, tenant=tenant), dev_index

    candidate_keys = (
        "deviceID",
        "deviceId",
        "serialNumber",
        "deviceSerialNo",
        "devSerial",
        "sn",
        "devName",
    )
    seen: set[str] = set()
    candidates: list[str] = []
    for source in (root, access_event):
        for key in candidate_keys:
            value = _event_value(source, key)
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            candidates.append(normalized)

    for candidate in candidates:
        device = _find_device_by_identifier(candidate, tenant=tenant)
        if device:
            return device, device.dev_index

    return None, ""


def _to_int(value):
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
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
        _event_value(access_event, "employeeNoString", "employee_no_string")
        or _event_value(access_event, "employeeNo", "employee_no")
        or _event_value(access_event, "cardNo", "card_no", "cardNumber")
        or ""
    )


def _attendance_status_value(access_event: dict) -> str:
    return str(_event_value(access_event, "attendanceStatus", "attendance_status") or "").strip()


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


def _should_create_attendance_log(
    access_event: dict,
    *,
    person_hint: str,
    attendance_status: str,
) -> bool:
    normalized_status = attendance_status.lower()
    if normalized_status and normalized_status != "undefined":
        return True

    if person_hint:
        return True

    sub_event_type = _to_int(access_event.get("subEventType"))
    if sub_event_type in AUTH_SUCCESS_SUB_TYPES:
        return True

    return False


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
    if not isinstance(root, dict):
        return None, None

    access_event = _extract_access_event(root)
    event_type = _normalize_event_type(_event_value(root, "eventType", "event_type"))
    if event_type != "AccessControllerEvent":
        if not access_event or not _looks_like_access_event(access_event):
            return None, None
        event_type = "AccessControllerEvent"

    access_event = _normalize_access_event(access_event, root)
    device, dev_index = _resolve_device_from_payload(root, access_event, tenant=tenant)
    if not dev_index:
        return None, None

    tenant_for_event = device.tenant if device else tenant
    if not tenant_for_event:
        return None, None

    timestamp_raw = _coalesce(
        _event_value(root, "dateTime", "time", "eventTime"),
        _event_value(access_event, "dateTime", "time", "eventTime"),
    )
    event_dt = _as_aware(parse_datetime(timestamp_raw or ""))
    person_hint = _person_hint(access_event)
    serial_no = str(
        _coalesce(
            _event_value(access_event, "serialNo", "serial_no"),
            _event_value(root, "serialNo", "serial_no"),
        )
        or ""
    )
    resolved_employee = None
    resolved_person_id = person_hint
    if device is not None:
        resolved_employee, resolved_person_id = _resolve_employee(device, access_event)

    dedupe_key = _build_dedupe_key(tenant_for_event.id, dev_index, timestamp_raw or "", person_hint, serial_no)
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
                major_event_type=_to_int(_event_value(access_event, "majorEventType", "major_event_type", "major")),
                sub_event_type=_to_int(_event_value(access_event, "subEventType", "sub_event_type", "minor")),
                serial_no=_to_int(_coalesce(_event_value(access_event, "serialNo", "serial_no"), _event_value(root, "serialNo", "serial_no"))),
                front_serial_no=_to_int(
                    _coalesce(
                        _event_value(access_event, "frontSerialNo", "front_serial_no"),
                        _event_value(root, "frontSerialNo", "front_serial_no"),
                    )
                ),
                employee_no=str(_event_value(access_event, "employeeNo", "employee_no") or ""),
                employee_no_string=str(
                    _coalesce(
                        _event_value(access_event, "employeeNoString", "employee_no_string"),
                        _event_value(access_event, "employeeNo", "employee_no"),
                    )
                    or ""
                ),
                card_no=str(_event_value(access_event, "cardNo", "card_no", "cardNumber") or ""),
                card_reader_no=_to_int(access_event.get("cardReaderNo")),
                door_no=_to_int(access_event.get("doorNo")),
                attendance_status=attendance_status,
                dedupe_key=dedupe_key,
                payload=payload,
            )

            if device is None:
                return raw_event, None

            if not _should_create_attendance_log(
                access_event,
                person_hint=person_hint,
                attendance_status=attendance_status,
            ):
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
