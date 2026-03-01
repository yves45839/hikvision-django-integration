from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from hik_gateway.models import Device
from hik_gateway.services.device_payload import extract_devices, normalize_device
from hik_gateway.services.gateway_connection import get_shared_gateway_client
from tenants.models import Tenant


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, dt_timezone.utc)
    return dt


def sync_gateway_devices(tenant=None) -> int:
    if tenant is None:
        return 0

    client = get_shared_gateway_client(tenant_code=tenant.code)
    response = client.device_list_all()
    items = extract_devices(response)

    synced = 0
    for item in items:
        normalized = normalize_device(item)
        dev_index = normalized["dev_index"]
        serial_number = normalized["serial_number"]
        if not dev_index or not serial_number:
            continue

        last_seen = _as_aware(parse_datetime(item.get("lastOnlineTime", "")))
        Device.objects.update_or_create(
            tenant=tenant,
            dev_index=dev_index,
            defaults={
                "tenant": tenant,
                "serial_number": serial_number,
                "device_id": item.get("deviceID", "") or item.get("deviceId", ""),
                "device_name": normalized["device_name"],
                "protocol_type": normalized["protocol_type"],
                "status": normalized["status"],
                "offline_hint": item.get("offlineReason", ""),
                "last_seen_at": last_seen,
            },
        )
        synced += 1

    return synced


def sync_all_gateways() -> int:
    # Single shared gateway connection: resync known devices by tenant mapping.
    total = 0
    tenant_ids = Device.objects.values_list("tenant_id", flat=True).distinct()
    for tenant in Tenant.objects.filter(id__in=tenant_ids).iterator():
        total += sync_gateway_devices(tenant)
    return total
