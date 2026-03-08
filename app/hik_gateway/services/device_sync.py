from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from hik_gateway.models import Device, Gateway
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

    gateway = Gateway.objects.filter(tenant=tenant).order_by("id").first()
    if gateway is None:
        base_url = (getattr(settings, "HIK_DEVICE_GATEWAY_BASE_URL", "") or "").strip()
        username = (getattr(settings, "HIK_DEVICE_GATEWAY_USERNAME", "") or "").strip()
        password = (getattr(settings, "HIK_DEVICE_GATEWAY_PASSWORD", "") or "").strip()
        if base_url and username and password:
            gateway = Gateway.objects.create(
                tenant=tenant,
                base_url=base_url,
                username=username,
                password=password,
            )

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
                "gateway": gateway,
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
    # Initial sync must not depend on existing devices.
    #
    # When DB gateways exist, sync only tenants that have at least one gateway row.
    # When using settings-based singleton credentials (no Gateway row), sync every
    # tenant because each tenant still needs local Device mapping.
    total = 0
    if Tenant.objects.filter(hik_gateways__isnull=False).exists():
        tenants = Tenant.objects.filter(hik_gateways__isnull=False).distinct()
    else:
        tenants = Tenant.objects.all()

    for tenant in tenants.iterator():
        total += sync_gateway_devices(tenant)
    return total
