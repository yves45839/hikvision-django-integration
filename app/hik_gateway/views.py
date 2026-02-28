from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from hik_gateway.client import HikGatewayClient
from hik_gateway.models import AttendanceLog, Gateway
from hik_gateway.services.device_payload import extract_devices, normalize_device
from hik_gateway.services.webhook_ingest import ingest_event
from tenants.models import Tenant


logger = logging.getLogger(__name__)


DEFAULT_DEVICE_LIST_PAYLOAD = {
    "SearchDescription": {
        "position": 0,
        "maxResult": 100,
        "Filter": {
            "key": "",
            "devType": "",
            "protocolType": ["ehomeV5"],
            "devStatus": ["online", "offline"],
        },
    }
}


def _client_ip(request: HttpRequest) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _is_allowed_ip(ip: str) -> bool:
    allowed = getattr(settings, "HIK_GATEWAY_ALLOWED_IPS", [])
    if not allowed:
        return True
    return ip in allowed


def _resolve_tenant(request: HttpRequest, payload: dict) -> Tenant | None:
    tenant_code = request.headers.get("X-TENANT-CODE", "").strip()
    root = payload.get("EventNotificationAlert", payload) if isinstance(payload, dict) else {}
    if not tenant_code and isinstance(root, dict):
        tenant_code = str(root.get("tenantCode") or payload.get("tenantCode") or "").strip()

    if not tenant_code:
        return None

    return Tenant.objects.filter(code=tenant_code).first()


def _is_allowed_token(request: HttpRequest) -> bool:
    expected = getattr(settings, "HIK_GATEWAY_WEBHOOK_TOKEN", "")
    if not expected:
        return True
    provided = request.headers.get("X-HIK-TOKEN", "")
    return provided == expected


@csrf_exempt
@require_POST
def hik_event_webhook(request: HttpRequest) -> JsonResponse:
    ip = _client_ip(request)
    if not _is_allowed_ip(ip) or not _is_allowed_token(request):
        return JsonResponse({"detail": "Unauthorized source"}, status=403)

    raw_body = request.body.decode("utf-8", errors="replace")
    logger.info("Hikvision webhook payload received", extra={"client_ip": ip, "raw_body": raw_body})

    try:
        payload = json.loads(raw_body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    tenant = _resolve_tenant(request, payload)
    if request.headers.get("X-TENANT-CODE") and tenant is None:
        return JsonResponse({"detail": "Unknown tenant"}, status=400)

    raw_event, attendance = ingest_event(payload, source=AttendanceLog.SOURCE_REALTIME, tenant=tenant)
    if raw_event is None:
        return JsonResponse({"status": "ignored"}, status=202)

    return JsonResponse(
        {
            "status": "ok",
            "raw_event_id": raw_event.id,
            "attendance_log_id": attendance.id if attendance else None,
        },
        status=201,
    )


def _is_admin_request(request: HttpRequest) -> bool:
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


@require_GET
def hik_devices_page(request: HttpRequest):
    tenant_code = (request.GET.get("tenant") or "").strip()
    is_admin = _is_admin_request(request)

    request_parameters = request.GET.get("request", "").strip() or json.dumps(
        DEFAULT_DEVICE_LIST_PAYLOAD,
        ensure_ascii=False,
        indent=2,
    )
    context = {
        "devices": [],
        "tenant_code": tenant_code,
        "error": "",
        "is_admin": is_admin,
        "request_parameters": request_parameters,
        "response_parameters": "",
        "status_code": "-",
        "gateway_url": "",
    }

    if tenant_code:
        gateways = Gateway.objects.select_related("tenant").filter(tenant__code__iexact=tenant_code).order_by("id")
    elif is_admin:
        gateways = Gateway.objects.select_related("tenant").all().order_by("tenant__code", "id")
    else:
        context["error"] = "Ajoute ?tenant=<code_tenant> (ou connecte-toi en administrateur pour voir tous les appareils)."
        return render(request, "hik_gateway/device_list.html", context, status=403)

    if not gateways.exists():
        if tenant_code:
            context["error"] = f"Aucune gateway trouvée pour le tenant '{tenant_code}'."
        else:
            context["error"] = "Aucune gateway configurée."
        return render(request, "hik_gateway/device_list.html", context)

    devices = []
    errors = []
    response_payload: dict | None = None

    try:
        payload_to_send = json.loads(request_parameters)
    except json.JSONDecodeError:
        context["error"] = "Request Parameters doit être un JSON valide."
        return render(request, "hik_gateway/device_list.html", context, status=400)

    for gateway in gateways:
        client = HikGatewayClient(gateway.base_url, gateway.username, gateway.password)
        context["gateway_url"] = gateway.base_url
        try:
            payload = client.device_list(payload=payload_to_send)
            response_payload = payload
            context["status_code"] = 200
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{gateway.tenant.code}: {exc}")
            continue

        for item in extract_devices(payload):
            normalized = normalize_device(item)
            normalized["tenant_code"] = gateway.tenant.code
            normalized["gateway_base_url"] = gateway.base_url
            devices.append(normalized)

    if response_payload is not None:
        context["response_parameters"] = json.dumps(response_payload, ensure_ascii=False, indent=2)

    if errors and not devices:
        context["error"] = "Impossible de récupérer les devices: " + " | ".join(errors)
    elif errors:
        context["error"] = "Certaines gateways ont échoué: " + " | ".join(errors)

    context["devices"] = devices
    return render(request, "hik_gateway/device_list.html", context)
