from __future__ import annotations

import logging
import time

from django.db import IntegrityError, OperationalError, transaction

from devices.models import Device as CoreDevice
from hik_gateway.models import Device as GatewayDevice


DEFAULT_GATEWAY_IP = "213.156.133.202"
DEFAULT_GATEWAY_PORT = 7661
DEFAULT_PROTOCOL = "ISUP"
_WRITE_RETRIES = 5
_LOCK_BACKOFF_SECONDS = 0.1

logger = logging.getLogger(__name__)


def _is_locked_error(exc: OperationalError) -> bool:
    return "database is locked" in str(exc).lower()


def _update_core_device_from_hik(*, core_device: CoreDevice, hik_device: GatewayDevice) -> None:
    core_device.tenant = hik_device.tenant
    core_device.device_id = hik_device.device_id
    if not core_device.name:
        core_device.name = hik_device.device_name
    core_device.model = ""
    core_device.protocol = hik_device.protocol_type or DEFAULT_PROTOCOL
    core_device.status = hik_device.status
    core_device.ip_address = DEFAULT_GATEWAY_IP
    core_device.port = DEFAULT_GATEWAY_PORT

    existing_same_dev_index = CoreDevice.objects.filter(dev_index=hik_device.dev_index).exclude(pk=core_device.pk).exists()
    if not existing_same_dev_index:
        core_device.dev_index = hik_device.dev_index

    existing_same_serial = CoreDevice.objects.filter(serial_number=hik_device.serial_number).exclude(pk=core_device.pk).exists()
    if not existing_same_serial:
        core_device.serial_number = hik_device.serial_number

    core_device.save()


def _dispatch_one(hik_device: GatewayDevice) -> bool:
    defaults = {
        "tenant": hik_device.tenant,
        "serial_number": hik_device.serial_number,
        "device_id": hik_device.device_id,
        "model": "",
        "protocol": hik_device.protocol_type or DEFAULT_PROTOCOL,
        "status": hik_device.status,
        "ip_address": DEFAULT_GATEWAY_IP,
        "port": DEFAULT_GATEWAY_PORT,
    }

    for attempt in range(_WRITE_RETRIES):
        try:
            core_device, created = CoreDevice.objects.update_or_create(
                dev_index=hik_device.dev_index,
                defaults=defaults,
            )
            if (created or not core_device.name) and hik_device.device_name:
                core_device.name = hik_device.device_name
                core_device.save(update_fields=["name"])
            return True
        except IntegrityError:
            try:
                with transaction.atomic():
                    by_serial = CoreDevice.objects.filter(serial_number=hik_device.serial_number).first()
                    if by_serial is not None:
                        _update_core_device_from_hik(core_device=by_serial, hik_device=hik_device)
                        return True

                    by_index = CoreDevice.objects.filter(dev_index=hik_device.dev_index).first()
                    if by_index is not None:
                        _update_core_device_from_hik(core_device=by_index, hik_device=hik_device)
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
                    "Skipped conflicting core device dispatch hik_device_id=%s dev_index=%s serial=%s",
                    hik_device.id,
                    hik_device.dev_index,
                    hik_device.serial_number,
                )
                return False
            time.sleep(_LOCK_BACKOFF_SECONDS * (attempt + 1))
        except OperationalError as exc:
            if _is_locked_error(exc) and attempt < _WRITE_RETRIES - 1:
                time.sleep(_LOCK_BACKOFF_SECONDS * (attempt + 1))
                continue
            raise

    return False


def dispatch_hik_devices_to_core_devices() -> int:
    """Dispatch gateway-synced devices into the core devices table per tenant."""
    dispatched = 0

    for hik_device in GatewayDevice.objects.select_related("tenant").all().iterator():
        dispatched += int(_dispatch_one(hik_device))

    return dispatched
