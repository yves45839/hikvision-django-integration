"""Admin dashboard for Phase 7 — Observabilité (7.3)."""

import datetime
from django.contrib.auth import get_user_model
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.urls import path
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

User = get_user_model()


class AdminDashboardView(View):
    """Dashboard métriques globales — accès staff uniquement."""

    @method_decorator(staff_member_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        from tenants.models import Tenant

        now = timezone.now()
        thirty_days_ago = now - datetime.timedelta(days=30)

        # MAU — utilisateurs ayant eu une activité dans les 30 derniers jours
        mau = User.objects.filter(last_login__gte=thirty_days_ago, is_active=True).count()

        # Signups (nouveaux tenants 30 derniers jours)
        signups_30d = Tenant.objects.filter(created_at__gte=thirty_days_ago).count()
        signups_total = Tenant.objects.count()

        # Tenants actifs
        active_tenants = Tenant.objects.filter(is_active=True).count()
        inactive_tenants = Tenant.objects.filter(is_active=False).count()

        # Churn 30j — tenants désactivés dans les 30 derniers jours
        churn_30d = 0  # placeholder — enrichir si un champ deactivated_at existe

        # MRR placeholder — à enrichir quand Stripe (Phase 3) sera implémenté
        mrr = 0

        # Devices
        try:
            from devices.models import Device
            total_devices = Device.objects.count()
            devices_by_tenant = list(
                Device.objects
                .values("tenant_code")
                .annotate(
                    count=__import__("django.db.models", fromlist=["Count"]).Count("id")
                )
                .order_by("-count")[:10]
            )
        except Exception:
            total_devices = 0
            devices_by_tenant = []

        # Employees
        try:
            from employees.models import Employee
            total_employees = Employee.objects.count()
        except Exception:
            total_employees = 0

        # Events récents
        try:
            from hik_gateway.models import HikWebhookLog
            events_30d = HikWebhookLog.objects.filter(created_at__gte=thirty_days_ago).count()
        except Exception:
            events_30d = 0

        return JsonResponse({
            "generated_at": now.isoformat(),
            "period_days": 30,
            "users": {
                "mau": mau,
                "total_active": User.objects.filter(is_active=True).count(),
            },
            "tenants": {
                "active": active_tenants,
                "inactive": inactive_tenants,
                "signups_30d": signups_30d,
                "signups_total": signups_total,
                "churn_30d": churn_30d,
            },
            "billing": {
                "mrr": mrr,
                "note": "MRR disponible après intégration Stripe (Phase 3)",
            },
            "devices": {
                "total": total_devices,
                "top_tenants": devices_by_tenant,
            },
            "employees": {
                "total": total_employees,
            },
            "events": {
                "last_30d": events_30d,
            },
        })
