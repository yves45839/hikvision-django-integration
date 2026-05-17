from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from devices.models import Device
from employees.models import Employee
from hik_gateway.models import AttendanceLog


def _resolve_lang(request) -> str:
    lang = str(request.query_params.get("lang") or "").strip().lower()
    if lang in {"fr", "en"}:
        return lang
    accept = str(request.headers.get("Accept-Language") or "").lower()
    if accept.startswith("en"):
        return "en"
    return "fr"


@api_view(["GET"])
def home_summary_api(request):
    lang = _resolve_lang(request)
    tenant_code = str(request.query_params.get("tenant") or "").strip()

    employees_qs = Employee.objects.all()
    devices_qs = Device.objects.all()
    logs_qs = AttendanceLog.objects.all()

    if tenant_code:
        employees_qs = employees_qs.filter(tenant__code=tenant_code)
        devices_qs = devices_qs.filter(tenant__code=tenant_code)
        logs_qs = logs_qs.filter(tenant__code=tenant_code)

    today = timezone.localdate()
    today_logs = logs_qs.filter(timestamp__date=today)
    online_devices = devices_qs.filter(status__iexact="online")

    payload = {
        "lang": lang,
        "tenant": tenant_code or None,
        "generated_at": timezone.now().isoformat(),
        "summary": {
            "employees_total": employees_qs.count(),
            "employees_active": employees_qs.filter(is_active=True).count(),
            "devices_total": devices_qs.count(),
            "devices_online": online_devices.count(),
            "attendance_logs_today": today_logs.count(),
            "denied_today": today_logs.filter(normalized_action=AttendanceLog.ACTION_ACCESS_DENIED).count(),
        },
        "labels": {
            "title": "Home summary" if lang == "en" else "Résumé accueil",
            "employees_total": "Total employees" if lang == "en" else "Employés total",
            "employees_active": "Active employees" if lang == "en" else "Employés actifs",
            "devices_total": "Total devices" if lang == "en" else "Appareils total",
            "devices_online": "Online devices" if lang == "en" else "Appareils en ligne",
            "attendance_logs_today": "Attendance logs today" if lang == "en" else "Pointages aujourd'hui",
            "denied_today": "Denied access today" if lang == "en" else "Accès refusés aujourd'hui",
        },
    }
    return Response(payload)
