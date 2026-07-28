from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone as dt_timezone

import requests
import logging
from django.conf import settings
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from hik_gateway.models import Device, DeviceCursor
from hik_gateway.services.gateway_connection import get_shared_gateway_client
from hik_gateway.services.webhook_ingest import ingest_acs_event

logger = logging.getLogger(__name__)


def _format_gateway_datetime(value: datetime) -> str:
    """
    The gateway rejects timestamps containing timezone offsets in AcsEventCond.
    Send naive UTC datetimes in the accepted format: YYYY-MM-DDTHH:MM:SS.
    """
    if timezone.is_aware(value):
        value = value.astimezone(dt_timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=0).isoformat()


def _extract_acs_info(payload: dict) -> tuple[list[dict], int]:
    info = payload.get("AcsEventTotalNum") or payload.get("AcsEvent") or payload
    events = info.get("InfoList", [])
    returned = info.get("numOfMatches")
    if isinstance(events, dict):
        events = events.get("AcsEventInfo", [])

    normalized_events = events if isinstance(events, list) else []
    if returned is None:
        returned = len(normalized_events)
    try:
        returned_count = int(returned)
    except (TypeError, ValueError):
        returned_count = len(normalized_events)
    if returned_count < 0:
        returned_count = len(normalized_events)

    return normalized_events, returned_count


def _extract_total_matches(payload: dict) -> int | None:
    info = payload.get("AcsEventTotalNum") or payload.get("AcsEvent") or payload
    if not isinstance(info, dict):
        return None
    total = info.get("totalMatches")
    try:
        parsed = int(total)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _is_bad_json_error(exc: Exception) -> bool:
    if not isinstance(exc, requests.HTTPError):
        return False
    message = str(exc).lower()
    return "badjsoncontent" in message or "wrong json content" in message


def _is_device_offline_error(exc: Exception) -> bool:
    if not isinstance(exc, requests.HTTPError):
        return False
    message = str(exc).lower()
    return "thedeviceisoffline" in message or "device is offline" in message


def _to_int(value) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _event_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, dt_timezone.utc)
    return parsed


def _catchup_lookback_hours() -> int:
    try:
        hours = int(getattr(settings, "HIK_CATCHUP_LOOKBACK_HOURS", 24))
    except (TypeError, ValueError):
        return 24
    return max(1, hours)


def _fast_active_hours() -> int:
    try:
        hours = int(getattr(settings, "HIK_CATCHUP_FAST_ACTIVE_HOURS", 48))
    except (TypeError, ValueError):
        return 48
    return max(1, hours)


def catchup_device(device: Device, max_results: int = 50) -> int:
    cursor, _ = DeviceCursor.objects.get_or_create(device=device, defaults={"tenant": device.tenant})
    initial_last_event_time = cursor.last_event_time
    initial_last_serial_no = cursor.last_serial_no

    now = timezone.now()
    lookback_floor = now - timedelta(hours=_catchup_lookback_hours())
    if cursor.last_event_time is None:
        start_time = lookback_floor
    else:
        start_time = max(cursor.last_event_time - timedelta(minutes=2), lookback_floor)
    end_time = now
    # Start each catchup window from position 0 to avoid skipping recent events.
    # Reusing a stale search position from a previous window can miss new pointages.
    search_id = f"{device.tenant_id}-{device.dev_index}-{int(now.timestamp())}"
    position = 0

    client = get_shared_gateway_client(tenant_code=device.tenant.code)

    processed = 0
    max_processed_time = cursor.last_event_time
    max_serial_no = cursor.last_serial_no
    window_fallback_used = False

    while True:
        condition_with_window = {
            "AcsEventCond": {
                "searchID": search_id,
                "searchResultPosition": position,
                "maxResults": max_results,
                "startTime": _format_gateway_datetime(start_time),
                "endTime": _format_gateway_datetime(end_time),
            }
        }
        condition_without_window = {
            "AcsEventCond": {
                "searchID": search_id,
                "searchResultPosition": position,
                "maxResults": max_results,
            }
        }
        try:
            response = client.acs_event_search(device.dev_index, condition_with_window)
        except Exception as exc:  # noqa: BLE001
            if not _is_bad_json_error(exc):
                raise
            window_fallback_used = True
            response = client.acs_event_search(device.dev_index, condition_without_window)
        events, returned = _extract_acs_info(response)
        total_matches = _extract_total_matches(response)
        if not events:
            break

        for event in events:
            raw_event, _ = ingest_acs_event(device, event)
            if raw_event:
                if raw_event.serial_no is not None and (max_serial_no is None or raw_event.serial_no > max_serial_no):
                    max_serial_no = raw_event.serial_no
            if raw_event:
                processed += 1
                event_time = raw_event.event_datetime
                if max_processed_time is None or event_time > max_processed_time:
                    max_processed_time = event_time

        position += returned
        if returned <= 0:
            break
        if total_matches is not None:
            if position >= total_matches:
                break
        elif returned < max_results:
            break

    serial_advanced = (
        max_serial_no is not None
        and (initial_last_serial_no is None or max_serial_no > initial_last_serial_no)
    )
    time_advanced = (
        max_processed_time is not None
        and (initial_last_event_time is None or max_processed_time > initial_last_event_time)
    )
    should_tail_resync = (
        (initial_last_event_time is not None or initial_last_serial_no is not None)
        and not serial_advanced
        and not time_advanced
        and window_fallback_used
    )

    if should_tail_resync:
        tail_search_id = f"{search_id}-tail"
        tail_head_payload = {
            "AcsEventCond": {
                "searchID": tail_search_id,
                "searchResultPosition": 0,
                "maxResults": max_results,
            }
        }
        tail_head_response = client.acs_event_search(device.dev_index, tail_head_payload)
        total_matches = _extract_total_matches(tail_head_response) or 0
        tail_position = max(total_matches - max_results, 0)
        if tail_position > 0:
            tail_payload = {
                "AcsEventCond": {
                    "searchID": tail_search_id,
                    "searchResultPosition": tail_position,
                    "maxResults": max_results,
                }
            }
            tail_response = client.acs_event_search(device.dev_index, tail_payload)
        else:
            tail_response = tail_head_response

        tail_events, _ = _extract_acs_info(tail_response)
        for event in tail_events:
            raw_event, _ = ingest_acs_event(device, event)
            if raw_event:
                if raw_event.serial_no is not None and (max_serial_no is None or raw_event.serial_no > max_serial_no):
                    max_serial_no = raw_event.serial_no
                processed += 1
                event_time = raw_event.event_datetime
                if max_processed_time is None or event_time > max_processed_time:
                    max_processed_time = event_time
        position = max(position, tail_position + len(tail_events))

    cursor.last_event_time = max_processed_time or cursor.last_event_time
    cursor.last_search_id = search_id
    cursor.last_search_result_position = position
    cursor.last_serial_no = max_serial_no
    cursor.save(update_fields=["last_event_time", "last_search_id", "last_search_result_position", "last_serial_no", "updated_at"])
    return processed


def catchup_device_tail(device: Device, max_results: int = 30) -> int:
    """
    Lightweight catchup for near-real-time refresh.
    Fetch only the latest tail page and skip events clearly older than cursor.
    """
    cursor, _ = DeviceCursor.objects.get_or_create(device=device, defaults={"tenant": device.tenant})
    client = get_shared_gateway_client(tenant_code=device.tenant.code)

    search_id = f"{device.tenant_id}-{device.dev_index}-{int(timezone.now().timestamp())}-tail"
    position = 0
    payload = {
        "AcsEventCond": {
            "searchID": search_id,
            "searchResultPosition": 0,
            "maxResults": max_results,
        }
    }
    response = client.acs_event_search(device.dev_index, payload)
    total_matches = _extract_total_matches(response)
    if total_matches is not None and total_matches > max_results:
        position = total_matches - max_results
        payload = {
            "AcsEventCond": {
                "searchID": search_id,
                "searchResultPosition": position,
                "maxResults": max_results,
            }
        }
        response = client.acs_event_search(device.dev_index, payload)

    events, returned = _extract_acs_info(response)
    if not events:
        cursor.last_search_id = search_id
        cursor.last_search_result_position = position
        cursor.save(update_fields=["last_search_id", "last_search_result_position", "updated_at"])
        return 0

    last_serial_no = cursor.last_serial_no
    last_event_time = cursor.last_event_time
    max_serial_no = last_serial_no
    max_event_time = last_event_time
    processed = 0

    for event in events:
        serial_no = _to_int(event.get("serialNo"))
        event_time = _event_time(str(event.get("time") or event.get("dateTime") or ""))
        if (
            last_serial_no is not None
            and serial_no is not None
            and serial_no <= last_serial_no
            and (last_event_time is None or (event_time is not None and event_time <= last_event_time))
        ):
            continue

        raw_event, _ = ingest_acs_event(device, event)
        if not raw_event:
            continue
        processed += 1
        if raw_event.serial_no is not None and (max_serial_no is None or raw_event.serial_no > max_serial_no):
            max_serial_no = raw_event.serial_no
        if max_event_time is None or raw_event.event_datetime > max_event_time:
            max_event_time = raw_event.event_datetime

    cursor.last_event_time = max_event_time or cursor.last_event_time
    cursor.last_search_id = search_id
    cursor.last_search_result_position = position + max(returned, len(events))
    cursor.last_serial_no = max_serial_no
    cursor.save(update_fields=["last_event_time", "last_search_id", "last_search_result_position", "last_serial_no", "updated_at"])
    return processed


def catchup_all_devices(max_results: int = 50) -> int:
    total = 0
    for device in Device.objects.select_related("tenant").all().iterator():
        try:
            total += catchup_device(device, max_results=max_results)
        except Exception as exc:  # noqa: BLE001
            if _is_device_offline_error(exc):
                logger.info(
                    "Skipping catchup for offline device",
                    extra={"dev_index": device.dev_index, "tenant_code": device.tenant.code},
                )
                continue
            raise
    return total


def catchup_tenant_devices(tenant_code: str, max_results: int = 50) -> int:
    total = 0
    for device in Device.objects.select_related("tenant").filter(tenant__code__iexact=tenant_code).iterator():
        try:
            total += catchup_device(device, max_results=max_results)
        except Exception as exc:  # noqa: BLE001
            if _is_device_offline_error(exc):
                logger.info(
                    "Skipping catchup for offline device",
                    extra={"dev_index": device.dev_index, "tenant_code": device.tenant.code},
                )
                continue
            raise
    return total


def catchup_tenant_devices_fast(tenant_code: str, max_results: int = 30) -> int:
    active_floor = timezone.now() - timedelta(hours=_fast_active_hours())
    base_qs = Device.objects.select_related("tenant").filter(tenant__code__iexact=tenant_code)
    devices = list(
        base_qs.filter(
            Q(cursor__last_event_time__gte=active_floor) | Q(cursor__isnull=True)
        ).iterator()
    )
    if not devices:
        devices = list(base_qs.iterator())

    total = 0
    for device in devices:
        try:
            total += catchup_device_tail(device, max_results=max_results)
        except Exception as exc:  # noqa: BLE001
            if _is_device_offline_error(exc):
                logger.info(
                    "Skipping fast catchup for offline device",
                    extra={"dev_index": device.dev_index, "tenant_code": device.tenant.code},
                )
                continue
            raise
    return total
