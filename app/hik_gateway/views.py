from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from hik_gateway.client import HikGatewayClient  # backward-compatible import for tests
from hik_gateway.models import AttendanceLog, Device
from hik_gateway.services.device_payload import extract_devices, normalize_device
from hik_gateway.services.gateway_connection import get_shared_gateway_client
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


def _parse_csv_query_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _to_bool(value: str | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _is_admin_request(request: HttpRequest) -> bool:
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


@api_view(["GET"])
def hik_devices_api(request: HttpRequest) -> Response:
    tenant_code = (request.GET.get("tenant") or "").strip()
    protocol_query = (request.GET.get("protocol") or "").strip()
    status_query = (request.GET.get("status") or "").strip()
    dev_type = (request.GET.get("dev_type") or "").strip()
    key = (request.GET.get("key") or "").strip()
    normalized = _to_bool(request.GET.get("normalized", "1"))

    try:
        max_result = int(request.GET.get("max_result", 100))
    except ValueError:
        return Response({"detail": "max_result must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

    protocol_types = _parse_csv_query_list(protocol_query)
    statuses = _parse_csv_query_list(status_query)

    if not tenant_code and not _is_admin_request(request):
        return Response(
            {"detail": "Ajoute ?tenant=<code_tenant> (ou connecte-toi en administrateur pour voir tous les appareils)."},
            status=status.HTTP_403_FORBIDDEN,
        )

    devices = []
    errors = []

    tenant_by_dev_index = {
        dev_index: tenant__code
        for dev_index, tenant__code in Device.objects.select_related("tenant").values_list("dev_index", "tenant__code")
    }
    allowed_dev_indexes = None
    if tenant_code:
        allowed_dev_indexes = {
            dev_index
            for dev_index, mapped_tenant_code in tenant_by_dev_index.items()
            if str(mapped_tenant_code).lower() == tenant_code.lower()
        }
        if not allowed_dev_indexes:
            allowed_dev_indexes = None

    try:
        client = get_shared_gateway_client(tenant_code=tenant_code or None)
        payload = client.device_list_all(
            max_result=max_result,
            protocol_types=protocol_types or None,
            statuses=statuses or None,
            dev_type=dev_type,
            key=key,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unable to list devices from shared gateway")
        errors.append(str(exc))
        payload = {}

    gateway_payloads = [{"tenant_code": tenant_code or "*", "search_result": payload.get("SearchResult", {})}]

    for item in extract_devices(payload):
        normalized_item = normalize_device(item)
        dev_index_value = normalized_item.get("dev_index") or item.get("devIndex", "")
        if allowed_dev_indexes is not None and dev_index_value not in allowed_dev_indexes:
            continue

        normalized_item["sn"] = (item.get("EhomeParams", {}) or {}).get("EhomeID", "")
        normalized_item["devIndex"] = item.get("devIndex", "")
        normalized_item["name"] = item.get("devName") or item.get("deviceName") or ""
        normalized_item["model"] = item.get("devType") or item.get("deviceType") or ""
        normalized_item["version"] = item.get("devVersion") or ""
        normalized_item["dev_serial"] = item.get("devSerial") or item.get("serialNumber") or ""
        normalized_item["offline_hint"] = item.get("offlineHint") or item.get("offlineReason") or ""
        normalized_item["tenant_code"] = tenant_by_dev_index.get(dev_index_value, "")
        normalized_item["gateway_base_url"] = "shared"
        devices.append(normalized_item)

    if not normalized:
        return Response({"count": len(gateway_payloads), "results": gateway_payloads, "errors": errors})

    return Response({"count": len(devices), "results": devices, "errors": errors})


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

    if not tenant_code and not is_admin:
        context["error"] = "Ajoute ?tenant=<code_tenant> (ou connecte-toi en administrateur pour voir tous les appareils)."
        return render(request, "hik_gateway/device_list.html", context, status=403)

    devices = []
    errors = []
    response_payload: dict | None = None

    try:
        payload_to_send = json.loads(request_parameters)
    except json.JSONDecodeError:
        context["error"] = "Request Parameters doit être un JSON valide."
        return render(request, "hik_gateway/device_list.html", context, status=400)

    tenant_by_dev_index = {
        dev_index: tenant__code
        for dev_index, tenant__code in Device.objects.select_related("tenant").values_list("dev_index", "tenant__code")
    }
    allowed_dev_indexes = None
    if tenant_code:
        allowed_dev_indexes = {
            dev_index
            for dev_index, mapped_tenant_code in tenant_by_dev_index.items()
            if str(mapped_tenant_code).lower() == tenant_code.lower()
        }
        if not allowed_dev_indexes:
            allowed_dev_indexes = None

    try:
        client = get_shared_gateway_client(tenant_code=tenant_code or None)
        context["gateway_url"] = "shared"
        payload = client.device_list(payload=payload_to_send)
        response_payload = payload
        context["status_code"] = 200
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
        payload = {}

    for item in extract_devices(payload):
        normalized = normalize_device(item)
        dev_index_value = normalized.get("dev_index") or item.get("devIndex", "")
        if allowed_dev_indexes is not None and dev_index_value not in allowed_dev_indexes:
            continue
        normalized["tenant_code"] = tenant_by_dev_index.get(dev_index_value, "")
        normalized["gateway_base_url"] = "shared"
        devices.append(normalized)

    if response_payload is not None:
        context["response_parameters"] = json.dumps(response_payload, ensure_ascii=False, indent=2)

    if errors and not devices:
        context["error"] = "Impossible de récupérer les devices: " + " | ".join(errors)
    elif errors:
        context["error"] = "La connexion gateway a échoué: " + " | ".join(errors)

    context["devices"] = devices
    return render(request, "hik_gateway/device_list.html", context)


@require_GET
def hikdevice_devices_space(request: HttpRequest):
    """Interface simple pour visualiser les appareils disponibles sur HikDevice."""
    tenant_code = (request.GET.get("tenant") or "").strip()
    protocol_query = (request.GET.get("protocol") or "").strip()
    status_query = (request.GET.get("status") or "").strip()
    dev_type = (request.GET.get("dev_type") or "").strip()
    key = (request.GET.get("key") or "").strip()
    is_admin = _is_admin_request(request)

    protocol_types = _parse_csv_query_list(protocol_query)
    statuses = _parse_csv_query_list(status_query)

    context = {
        "devices": [],
        "tenant_code": tenant_code,
        "protocol": protocol_query,
        "status_filter": status_query,
        "dev_type": dev_type,
        "key": key,
        "error": "",
        "is_admin": is_admin,
    }

    if not tenant_code and not is_admin:
        context["error"] = "Ajoute ?tenant=<code_tenant> (ou connecte-toi en administrateur pour voir tous les appareils)."
        return render(request, "hik_gateway/hikdevice_devices_space.html", context, status=403)

    tenant_by_dev_index = {
        dev_index: tenant__code
        for dev_index, tenant__code in Device.objects.select_related("tenant").values_list("dev_index", "tenant__code")
    }

    allowed_dev_indexes = None
    if tenant_code:
        allowed_dev_indexes = {
            dev_index
            for dev_index, mapped_tenant_code in tenant_by_dev_index.items()
            if str(mapped_tenant_code).lower() == tenant_code.lower()
        }
        if not allowed_dev_indexes:
            allowed_dev_indexes = None

    try:
        client = get_shared_gateway_client(tenant_code=tenant_code or None)
        payload = client.device_list_all(
            max_result=100,
            protocol_types=protocol_types or None,
            statuses=statuses or None,
            dev_type=dev_type,
            key=key,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unable to list devices in hikdevice devices space")
        context["error"] = f"Impossible de récupérer les appareils: {exc}"
        return render(request, "hik_gateway/hikdevice_devices_space.html", context, status=502)

    devices = []
    for item in extract_devices(payload):
        normalized_item = normalize_device(item)
        dev_index_value = normalized_item.get("dev_index") or item.get("devIndex", "")
        if allowed_dev_indexes is not None and dev_index_value not in allowed_dev_indexes:
            continue

        normalized_item["sn"] = (item.get("EhomeParams", {}) or {}).get("EhomeID", "")
        normalized_item["tenant_code"] = tenant_by_dev_index.get(dev_index_value, "")
        devices.append(normalized_item)

    context["devices"] = devices
    return render(request, "hik_gateway/hikdevice_devices_space.html", context)
