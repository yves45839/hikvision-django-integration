from __future__ import annotations

from devices.models import Device as CoreDevice
from hik_gateway.models import Device as GatewayDevice


DEFAULT_GATEWAY_IP = "213.156.133.202"
DEFAULT_GATEWAY_PORT = 7661
DEFAULT_PROTOCOL = "ISUP"


def dispatch_hik_devices_to_core_devices() -> int:
    """Dispatch gateway-synced devices into the core devices table per tenant."""
    dispatched = 0

    for hik_device in GatewayDevice.objects.select_related("tenant").all().iterator():
        CoreDevice.objects.update_or_create(
            dev_index=hik_device.dev_index,
            defaults={
                "tenant": hik_device.tenant,
                "serial_number": hik_device.serial_number,
                "device_id": hik_device.device_id,
                "name": hik_device.device_name,
                "model": "",
                "protocol": hik_device.protocol_type or DEFAULT_PROTOCOL,
                "status": hik_device.status,
                "ip_address": DEFAULT_GATEWAY_IP,
                "port": DEFAULT_GATEWAY_PORT,
            },
        )
        dispatched += 1

    return dispatched
