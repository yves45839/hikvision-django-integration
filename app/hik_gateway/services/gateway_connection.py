from __future__ import annotations

from django.conf import settings

from hik_gateway.client import HikGatewayClient
from hik_gateway.models import Gateway


def get_shared_gateway_client(*, tenant_code: str | None = None) -> HikGatewayClient:
    """Return a single HikDeviceGateway client configured at app level.

    Priority:
    1) Settings-based singleton connection (HIK_DEVICE_GATEWAY_*).
    2) Legacy DB fallback (first Gateway row, optionally filtered by tenant).
    """

    base_url = (getattr(settings, "HIK_DEVICE_GATEWAY_BASE_URL", "") or "").strip()
    username = (getattr(settings, "HIK_DEVICE_GATEWAY_USERNAME", "") or "").strip()
    password = (getattr(settings, "HIK_DEVICE_GATEWAY_PASSWORD", "") or "").strip()

    if base_url and username and password:
        return HikGatewayClient(base_url, username, password)

    gateways = Gateway.objects.select_related("tenant").filter(kind=Gateway.KIND_HIKVISION).order_by("id")
    if tenant_code:
        gateways = gateways.filter(tenant__code__iexact=tenant_code)

    gateway = gateways.first()
    if gateway is None:
        raise Gateway.DoesNotExist(
            "Aucune connexion HikDeviceGateway n'est configurée "
            "(HIK_DEVICE_GATEWAY_BASE_URL/USERNAME/PASSWORD)."
        )

    return HikGatewayClient(gateway.base_url, gateway.username, gateway.password)

