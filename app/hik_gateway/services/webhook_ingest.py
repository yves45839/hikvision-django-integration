from __future__ import annotations

import hashlib
from datetime import datetime, timezone as dt_timezone

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from hik_gateway.models import AttendanceLog, Device, RawEvent
from hik_gateway.services.device_sync import sync_gateway_devices

FALLBACK_ATTENDANCE = {
    (5, 75): "checkIn",
    (5, 76): "checkOut",
    (5, 77): "breakIn",
    (5, 78): "breakOut",
}


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


def _build_dedupe_key(dev_index: str, event_datetime: str, person_id: str, sub_event_type: str, serial_no: str) -> str:
    raw = "|".join([dev_index or "", event_datetime or "", person_id or "", sub_event_type or "", serial_no or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _resolve_attendance_type(access_event: dict) -> str:
    attendance_status = access_event.get("attendanceStatus")
    if attendance_status:
        return attendance_status

    major = access_event.get("majorEventType")
    minor = access_event.get("subEventType")
    if isinstance(major, str) and major.isdigit():
        major = int(major)
    if isinstance(minor, str) and minor.isdigit():
        minor = int(minor)

    return FALLBACK_ATTENDANCE.get((major, minor), "unknown")


def _get_or_resync_device(dev_index: str) -> Device | None:
    device = Device.objects.filter(dev_index=dev_index).select_related("gateway").first()
    if device:
        return device


    from hik_gateway.models import Gateway

    for gateway in Gateway.objects.all().iterator():
        sync_gateway_devices(gateway)
        device = Device.objects.filter(dev_index=dev_index).select_related("gateway").first()
        if device:
            return device
    return None


def ingest_event(payload: dict, source: str) -> tuple[RawEvent | None, AttendanceLog | None]:
    root = _event_root(payload)
    if root.get("eventType") != "AccessControllerEvent":
        return None, None

    access_event = root.get("AccessControllerEvent", {})
    dev_index = root.get("devIndex", "")
    if not dev_index:
        return None, None

    device = _get_or_resync_device(dev_index)
    if not device:
        return None, None

    timestamp_raw = root.get("dateTime") or access_event.get("time")
    event_dt = _as_aware(parse_datetime(timestamp_raw or ""))
    person_id = str(access_event.get("employeeNoString") or "")
    sub_event_type = str(access_event.get("subEventType") or "")
    serial_no = str(access_event.get("serialNo") or root.get("serialNo") or "")

    dedupe_key = _build_dedupe_key(dev_index, timestamp_raw or "", person_id, sub_event_type, serial_no)
    event_type = root.get("eventType", "")
    attendance_type = _resolve_attendance_type(access_event)

    with transaction.atomic():
        try:
            raw_event = RawEvent.objects.create(
                tenant=device.tenant,
                device=device,
                dev_index=dev_index,
                event_type=event_type,
                event_datetime=event_dt,
                dedupe_key=dedupe_key,
                payload=payload,
            )
        except IntegrityError:
            raw_event = RawEvent.objects.filter(dedupe_key=dedupe_key).first()
            if raw_event:
                attendance = AttendanceLog.objects.filter(raw_event=raw_event).first()
                return raw_event, attendance
            return None, None

        attendance = AttendanceLog.objects.create(
            tenant=device.tenant,
            person_id=person_id,
            device=device,
            timestamp=event_dt,
            attendance_type=attendance_type,
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
