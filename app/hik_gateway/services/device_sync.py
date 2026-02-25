from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from hik_gateway.client import HikGatewayClient
from hik_gateway.models import Device, Gateway


def _get_nested(data: dict, keys: list[str], default=None):
    node = data
    for key in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(key)
    return node if node is not None else default


def _extract_devices(payload: dict) -> list[dict]:
    candidates = [
        _get_nested(payload, ["DeviceList", "Device"], []),
        _get_nested(payload, ["DeviceList", "devices"], []),
        payload.get("Device") if isinstance(payload, dict) else [],
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return candidate
    return []


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, dt_timezone.utc)
    return dt


def sync_gateway_devices(gateway: Gateway) -> int:
    client = HikGatewayClient(gateway.base_url, gateway.username, gateway.password)
    response = client.device_list()
    items = _extract_devices(response)

    synced = 0
    for item in items:
        dev_index = item.get("devIndex") or item.get("devIndexCode")
        serial_number = item.get("serialNumber") or item.get("deviceSerialNo")
        if not dev_index or not serial_number:
            continue

        last_seen = _as_aware(parse_datetime(item.get("lastOnlineTime", "")))
        Device.objects.update_or_create(
            tenant=gateway.tenant,
            dev_index=dev_index,
            defaults={
                "gateway": gateway,
                "tenant": gateway.tenant,
                "serial_number": serial_number,
                "device_id": item.get("deviceID", "") or item.get("deviceId", ""),
                "device_name": item.get("deviceName", ""),
                "protocol_type": item.get("protocolType", ""),
                "status": item.get("status", ""),
                "offline_hint": item.get("offlineReason", ""),
                "last_seen_at": last_seen,
            },
        )
        synced += 1

    return synced


def sync_all_gateways() -> int:
    total = 0
    for gateway in Gateway.objects.all().iterator():
        total += sync_gateway_devices(gateway)
    return total
