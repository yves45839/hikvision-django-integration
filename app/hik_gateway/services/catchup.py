from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from hik_gateway.client import HikGatewayClient
from hik_gateway.models import AttendanceLog, Device, DeviceCursor
from hik_gateway.services.webhook_ingest import ingest_acs_event


def _extract_acs_info(payload: dict) -> tuple[list[dict], int]:
    info = payload.get("AcsEventTotalNum", payload)
    events = info.get("InfoList", [])
    total = info.get("totalMatches")
    if isinstance(events, dict):
        events = events.get("AcsEventInfo", [])
    if total is None:
        total = len(events)
    return events if isinstance(events, list) else [], int(total)


def catchup_device(device: Device, max_results: int = 50) -> int:
    cursor, _ = DeviceCursor.objects.get_or_create(device=device)

    now = timezone.now()
    start_time = (cursor.last_event_time or (now - timedelta(minutes=30))) - timedelta(minutes=2)
    end_time = now
    search_id = cursor.last_search_id or f"{device.tenant_id}-{device.dev_index}"
    position = 0

    client = HikGatewayClient(device.gateway.base_url, device.gateway.username, device.gateway.password)

    processed = 0
    max_processed_time = cursor.last_event_time

    while True:
        condition = {
            "AcsEventCond": {
                "searchID": search_id,
                "searchResultPosition": position,
                "maxResults": max_results,
                "startTime": start_time.isoformat(),
                "endTime": end_time.isoformat(),
            }
        }
        response = client.acs_event_search(device.dev_index, condition)
        events, returned = _extract_acs_info(response)
        if not events:
            break

        for event in events:
            raw_event, attendance = ingest_acs_event(device, event)
            if raw_event and attendance:
                processed += 1
                if max_processed_time is None or attendance.timestamp > max_processed_time:
                    max_processed_time = attendance.timestamp

        position += returned
        if returned < max_results:
            break

    cursor.last_event_time = max_processed_time or cursor.last_event_time
    cursor.last_search_id = search_id
    cursor.last_result_position = position
    cursor.save(update_fields=["last_event_time", "last_search_id", "last_result_position", "updated_at"])
    return processed


def catchup_all_devices(max_results: int = 50) -> int:
    total = 0
    for device in Device.objects.select_related("gateway", "tenant").all().iterator():
        total += catchup_device(device, max_results=max_results)
    return total
