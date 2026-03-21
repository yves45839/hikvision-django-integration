from __future__ import annotations

import logging
import time
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from hik_gateway.models import Device, Gateway
from hik_gateway.services.device_payload import extract_devices, normalize_device
from hik_gateway.services.gateway_connection import get_shared_gateway_client
from tenants.models import Tenant

logger = logging.getLogger(__name__)

_WRITE_RETRIES = 5
_LOCK_BACKOFF_SECONDS = 0.1


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, dt_timezone.utc)
    return dt


def _is_locked_error(exc: OperationalError) -> bool:
    return "database is locked" in str(exc).lower()


def _update_device_fields(
    *,
    device: Device,
    gateway,
    tenant,
    serial_number: str,
    dev_index: str,
    item: dict,
    normalized: dict,
    last_seen,
) -> None:
    device.gateway = gateway
    device.tenant = tenant
    device.device_id = item.get("deviceID", "") or item.get("deviceId", "")
    device.device_name = normalized["device_name"]
    device.protocol_type = normalized["protocol_type"]
    device.status = normalized["status"]
    device.offline_hint = item.get("offlineReason", "")
    device.last_seen_at = last_seen

    # Keep unique constraints stable even when upstream identifiers drift.
    existing_with_dev_index = Device.objects.filter(
        tenant=tenant,
        dev_index=dev_index,
    ).exclude(pk=device.pk).exists()
    if not existing_with_dev_index:
        device.dev_index = dev_index

    existing_with_serial = Device.objects.filter(
        tenant=tenant,
        serial_number=serial_number,
    ).exclude(pk=device.pk).exists()
    if not existing_with_serial:
        device.serial_number = serial_number

    device.save()


def _sync_one_device(*, tenant, gateway, item: dict, normalized: dict, last_seen) -> bool:
    dev_index = normalized["dev_index"]
    serial_number = normalized["serial_number"]
    defaults = {
        "gateway": gateway,
        "tenant": tenant,
        "serial_number": serial_number,
        "device_id": item.get("deviceID", "") or item.get("deviceId", ""),
        "device_name": normalized["device_name"],
        "protocol_type": normalized["protocol_type"],
        "status": normalized["status"],
        "offline_hint": item.get("offlineReason", ""),
        "last_seen_at": last_seen,
    }

    for attempt in range(_WRITE_RETRIES):
        try:
            Device.objects.update_or_create(
                tenant=tenant,
                dev_index=dev_index,
                defaults=defaults,
            )
            return True
        except IntegrityError:
            # Fallback for constraint conflicts between (tenant, dev_index) and (tenant, serial_number).
            try:
                with transaction.atomic():
                    by_serial = Device.objects.filter(tenant=tenant, serial_number=serial_number).first()
                    if by_serial is not None:
                        _update_device_fields(
                            device=by_serial,
                            gateway=gateway,
                            tenant=tenant,
                            serial_number=serial_number,
                            dev_index=dev_index,
                            item=item,
                            normalized=normalized,
                            last_seen=last_seen,
                        )
                        return True

                    by_index = Device.objects.filter(tenant=tenant, dev_index=dev_index).first()
                    if by_index is not None:
                        _update_device_fields(
                            device=by_index,
                            gateway=gateway,
                            tenant=tenant,
                            serial_number=serial_number,
                            dev_index=dev_index,
                            item=item,
                            normalized=normalized,
                            last_seen=last_seen,
                        )
                        return True
            except OperationalError as exc:
                if _is_locked_error(exc) and attempt < _WRITE_RETRIES - 1:
                    time.sleep(_LOCK_BACKOFF_SECONDS * (attempt + 1))
                    continue
                raise
            except IntegrityError:
                pass

            if attempt == _WRITE_RETRIES - 1:
                logger.warning(
                    "Skipped conflicting device during sync tenant=%s dev_index=%s serial=%s",
                    tenant.code,
                    dev_index,
                    serial_number,
                )
                return False
            time.sleep(_LOCK_BACKOFF_SECONDS * (attempt + 1))
        except OperationalError as exc:
            if _is_locked_error(exc) and attempt < _WRITE_RETRIES - 1:
                time.sleep(_LOCK_BACKOFF_SECONDS * (attempt + 1))
                continue
            raise

    return False


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
        synced += int(
            _sync_one_device(
                tenant=tenant,
                gateway=gateway,
                item=item,
                normalized=normalized,
                last_seen=last_seen,
            )
        )

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
