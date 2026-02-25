from __future__ import annotations

import hashlib
from datetime import datetime, timezone as dt_timezone

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

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

AUTH_SUCCESS_SUB_TYPES = {1, 2, 15, 16, 38, 40, 43, 46}
IGNORED_SUB_TYPES = {3, 6, 25, 26, 27, 28}
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


def _build_dedupe_key(dev_index: str, event_datetime: str, person_hint: str, serial_no: str) -> str:
    raw = "|".join([dev_index or "", event_datetime or "", person_hint or "", serial_no or ""])
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


def _resolve_direction(device: Device, access_event: dict) -> tuple[str, bool]:
    status = _attendance_status_value(access_event)
    normalized = status.lower()
    if normalized and normalized != "undefined":
        return ATTENDANCE_DIRECTION_MAP.get(normalized, "UNKNOWN"), True

    sub_event_type = _to_int(access_event.get("subEventType"))
    if sub_event_type in IGNORED_SUB_TYPES:
        return "IGNORE", False
    if sub_event_type == 23:
        return "OUT", False
    if sub_event_type in AUTH_SUCCESS_SUB_TYPES:
        door_no = _to_int(access_event.get("doorNo"))
        card_reader_no = _to_int(access_event.get("cardReaderNo"))
        if door_no is not None and card_reader_no is not None:
            reader_config = DeviceReaderConfig.objects.filter(
                device=device,
                door_no=door_no,
                card_reader_no=card_reader_no,
            ).first()
            if reader_config:
                return reader_config.direction_default, False
        return "IN", False

    return "UNKNOWN", False


def _connected_status_filter() -> Q:
    connected_filter = Q(status__iexact=CONNECTED_DEVICE_STATUSES[0])
    for status_value in CONNECTED_DEVICE_STATUSES[1:]:
        connected_filter |= Q(status__iexact=status_value)
    return connected_filter


def _get_or_resync_device(dev_index: str, tenant: Tenant | None = None) -> Device | None:
    queryset = Device.objects.filter(dev_index=dev_index)
    if tenant is not None:
        queryset = queryset.filter(tenant=tenant)

    device = queryset.filter(_connected_status_filter()).select_related("gateway").first()
    if device:
        return device

    from hik_gateway.models import Gateway

    gateways = Gateway.objects.all()
    if tenant is not None:
        gateways = gateways.filter(tenant=tenant)

    for gateway in gateways.iterator():
        sync_gateway_devices(gateway)
        device = (
            Device.objects.filter(gateway=gateway, dev_index=dev_index)
            .filter(_connected_status_filter())
            .select_related("gateway")
            .first()
        )
        if device:
            return device

    return queryset.select_related("gateway").first()


def ingest_event(payload: dict, source: str, tenant: Tenant | None = None) -> tuple[RawEvent | None, AttendanceLog | None]:
    root = _event_root(payload)
    if root.get("eventType") != "AccessControllerEvent":
        return None, None

    access_event = root.get("AccessControllerEvent", {})
    dev_index = root.get("devIndex", "")
    if not dev_index:
        return None, None

    device = _get_or_resync_device(dev_index, tenant=tenant)
    if not device:
        return None, None

    timestamp_raw = root.get("dateTime") or access_event.get("time")
    event_dt = _as_aware(parse_datetime(timestamp_raw or ""))
    person_hint = _person_hint(access_event)
    serial_no = str(access_event.get("serialNo") or root.get("serialNo") or "")

    dedupe_key = _build_dedupe_key(dev_index, timestamp_raw or "", person_hint, serial_no)
    event_type = root.get("eventType", "")
    attendance_status = _attendance_status_value(access_event)
    direction, from_status = _resolve_direction(device, access_event)

    with transaction.atomic():
        try:
            raw_event = RawEvent.objects.create(
                tenant=device.tenant,
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
        except IntegrityError:
            raw_event = RawEvent.objects.filter(dedupe_key=dedupe_key).first()
            if raw_event:
                attendance = AttendanceLog.objects.filter(raw_event=raw_event).first()
                return raw_event, attendance
            return None, None

        if direction == "IGNORE":
            return raw_event, None

        attendance = AttendanceLog.objects.create(
            tenant=device.tenant,
            person_id=person_hint,
            device=device,
            timestamp=event_dt,
            attendance_type=attendance_status or ("fallback" if not from_status else "unknown"),
            attendance_status=attendance_status,
            direction=direction,
            source=source,
            raw_event=raw_event,
        )
    return raw_event, attendance


def ingest_acs_event(device: Device, acs_event: dict) -> tuple[RawEvent | None, AttendanceLog | None]:
    wrapped = {
        "EventNotificationAlert": {
            "eventType": "AccessControllerEvent",
            "devIndex": device.dev_index,
            "dateTime": acs_event.get("dateTime") or acs_event.get("time"),
            "AccessControllerEvent": acs_event,
        }
    }
    return ingest_event(wrapped, source=AttendanceLog.SOURCE_CATCHUP)
