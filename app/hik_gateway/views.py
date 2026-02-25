from __future__ import annotations

import json

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from hik_gateway.models import AttendanceLog
from hik_gateway.services.webhook_ingest import ingest_event
from tenants.models import Tenant


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

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
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
