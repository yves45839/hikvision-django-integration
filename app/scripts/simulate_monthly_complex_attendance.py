import json
import os
import random
import sys
import argparse
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from employees.models import Employee, Planning, PlanningAssignment, PlanningEntry, WorkShift
from hik_gateway.models import AttendanceLog, Device, Gateway, RawEvent
from hik_gateway.views import hik_attendance_reports_api
from tenants.models import Tenant


SIM_PREFIX = "SIM-COMPLEX-MONTHLY"
RANDOM_SEED = 260319
TENANT_CODE = "sim-complex-monthly-tenant"
EMPLOYEE_NO = "SIM-COMPLEX-EMP-001"


def make_local_dt(target_day: date, value_time: time, day_offset: int = 0):
    current_tz = timezone.get_current_timezone()
    value = datetime.combine(target_day + timedelta(days=day_offset), value_time)
    return timezone.make_aware(value, current_tz)


def serialize_value(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, set):
        return sorted(list(value))
    return str(value)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    return first, last


def parse_args():
    today = timezone.localdate()
    parser = argparse.ArgumentParser(description="Simule un mois complet de pointages complexes.")
    parser.add_argument("--year", type=int, default=today.year, help="Annee cible (ex: 2026)")
    parser.add_argument("--month", type=int, default=today.month, help="Mois cible 1..12")
    return parser.parse_args()


def cleanup_previous_simulation():
    AttendanceLog.objects.filter(raw_event__dedupe_key__startswith=f"{SIM_PREFIX}:").delete()
    RawEvent.objects.filter(dedupe_key__startswith=f"{SIM_PREFIX}:").delete()
    PlanningAssignment.objects.filter(metadata__simulation=SIM_PREFIX).delete()
    PlanningEntry.objects.filter(planning__code__startswith=f"{SIM_PREFIX}-").delete()
    Planning.objects.filter(code__startswith=f"{SIM_PREFIX}-").delete()
    WorkShift.objects.filter(code__startswith=f"{SIM_PREFIX}-").delete()


def ensure_report_user():
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="sim_monthly_report_admin",
        defaults={
            "email": "sim_monthly_report_admin@example.local",
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
        },
    )
    if not user.is_staff or not user.is_superuser or not user.is_active:
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.save(update_fields=["is_staff", "is_superuser", "is_active"])
    return user


def ensure_tenant_gateway_and_device():
    tenant, _ = Tenant.objects.get_or_create(
        code=TENANT_CODE,
        defaults={
            "name": "Simulation Monthly Tenant",
            "is_active": True,
            "payment_status": "not_required",
        },
    )
    gateway, _ = Gateway.objects.get_or_create(
        tenant=tenant,
        base_url="https://sim-monthly.gateway.local",
        defaults={"username": "admin", "password": "pass"},
    )
    device, _ = Device.objects.get_or_create(
        tenant=tenant,
        dev_index=f"{SIM_PREFIX}-IDX-001",
        defaults={
            "gateway": gateway,
            "serial_number": f"{SIM_PREFIX}-SN-001",
            "device_id": f"{SIM_PREFIX}-DEV-001",
            "device_name": "Sim Monthly Reader",
            "protocol_type": "ehomeV5",
            "status": "online",
        },
    )
    if device.gateway_id != gateway.id:
        device.gateway = gateway
        device.save(update_fields=["gateway"])
    return tenant, gateway, device


def ensure_employee(tenant: Tenant, shifts: list[WorkShift]):
    employee, _ = Employee.objects.get_or_create(
        tenant=tenant,
        employee_no=EMPLOYEE_NO,
        defaults={
            "name": "Simulation Complex Monthly Employee",
            "is_active": True,
            "work_shift": shifts[0],
        },
    )
    if employee.work_shift_id != shifts[0].id:
        employee.work_shift = shifts[0]
        employee.save(update_fields=["work_shift"])
    employee.work_shifts.set(shifts)
    return employee


def create_attendance_log(*, tenant, device, employee, event_dt, direction, attendance_type, action):
    dedupe_key = f"{SIM_PREFIX}:{employee.employee_no}:{event_dt.isoformat()}:{direction}:{uuid4().hex[:10]}"
    raw = RawEvent.objects.create(
        tenant=tenant,
        device=device,
        dev_index=device.dev_index,
        event_type="SIMULATED",
        event_datetime=event_dt,
        major_event_type=5,
        sub_event_type=75,
        serial_no=None,
        front_serial_no=None,
        employee_no=employee.employee_no,
        employee_no_string=employee.employee_no,
        card_no="SIM-CARD",
        card_reader_no=1,
        door_no=1,
        attendance_status=attendance_type,
        dedupe_key=dedupe_key,
        payload={"simulation": SIM_PREFIX, "direction": direction, "action": action},
    )
    AttendanceLog.objects.create(
        tenant=tenant,
        employee=employee,
        person_id=employee.employee_no,
        device=device,
        timestamp=event_dt,
        attendance_type=attendance_type,
        attendance_status=attendance_type,
        normalized_action=action,
        direction=direction,
        source=AttendanceLog.SOURCE_REALTIME,
        raw_event=raw,
    )


def build_complex_planning(*, tenant: Tenant, month_start: date, shift_morning: WorkShift, shift_afternoon: WorkShift, shift_night: WorkShift):
    planning = Planning.objects.create(
        tenant=tenant,
        name="Simulation Rotation 3 Quarts (Mois complet)",
        code=f"{SIM_PREFIX}-PLANNING",
        description="Rotation continue 07h-14h / 14h-22h / 22h-06h, weekends inclus",
        timezone=str(timezone.get_current_timezone()),
        metadata={
            "simulation": SIM_PREFIX,
            "cycle_length_days": 3,
            "cycle_anchor_date": month_start.isoformat(),
        },
    )
    PlanningEntry.objects.create(
        planning=planning,
        sequence_index=0,
        work_shift=shift_morning,
        label="Quart matin 07h-14h",
        metadata={"simulation": SIM_PREFIX},
    )
    PlanningEntry.objects.create(
        planning=planning,
        sequence_index=1,
        work_shift=shift_afternoon,
        label="Quart apres-midi 14h-22h",
        metadata={"simulation": SIM_PREFIX},
    )
    PlanningEntry.objects.create(
        planning=planning,
        sequence_index=2,
        work_shift=shift_night,
        label="Quart nuit 22h-06h",
        metadata={"simulation": SIM_PREFIX},
    )
    return planning


def generate_monthly_logs(*, tenant: Tenant, device: Device, employee: Employee, month_start: date, month_end: date, shifts_cycle: list[WorkShift]):
    generator = random.Random(RANDOM_SEED)
    total_logs = 0
    weekend_days = 0

    current_day = month_start
    day_index = 0
    while current_day <= month_end:
        shift = shifts_cycle[day_index % len(shifts_cycle)]
        if current_day.weekday() >= 5:
            weekend_days += 1

        shift_start = make_local_dt(current_day, shift.start_time)
        shift_end_day = current_day if shift.end_time > shift.start_time else (current_day + timedelta(days=1))
        shift_end = make_local_dt(shift_end_day, shift.end_time)

        early_minutes = generator.randint(0, 30)
        overtime_minutes = generator.randint(0, 50)
        checkin_dt = shift_start - timedelta(minutes=early_minutes)
        checkout_dt = shift_end + timedelta(minutes=overtime_minutes)

        create_attendance_log(
            tenant=tenant,
            device=device,
            employee=employee,
            event_dt=checkin_dt,
            direction="IN",
            attendance_type="checkin",
            action=AttendanceLog.ACTION_CHECK_IN,
        )
        create_attendance_log(
            tenant=tenant,
            device=device,
            employee=employee,
            event_dt=checkout_dt,
            direction="OUT",
            attendance_type="checkout",
            action=AttendanceLog.ACTION_CHECK_OUT,
        )

        total_logs += 2
        current_day += timedelta(days=1)
        day_index += 1

    return {"total_logs": total_logs, "weekend_days": weekend_days}


def validate_report(*, response_payload: dict, employee_no: str, month_start: date, month_end: date, expected_total_logs: int, expected_weekend_days: int):
    total_days = (month_end - month_start).days + 1
    compliance_summary = (response_payload.get("compliance") or {}).get("summary") or {}
    compliance_employees = (response_payload.get("compliance") or {}).get("employees") or []
    if len(compliance_employees) != 1:
        raise RuntimeError(f"Rapport invalide: 1 employe attendu, recu={len(compliance_employees)}")

    employee_payload = compliance_employees[0]
    details = employee_payload.get("details") or []
    details_by_date = {item.get("date"): item for item in details}
    weekend_detail_count = sum(
        1
        for day_iso in details_by_date.keys()
        if date.fromisoformat(day_iso).weekday() >= 5
    )

    expected_shift_codes = {
        f"{SIM_PREFIX}-SHIFT-0714",
        f"{SIM_PREFIX}-SHIFT-1422",
        f"{SIM_PREFIX}-SHIFT-2206",
    }
    used_shift_codes = {
        ((item.get("matched_shift") or {}).get("code") or "").strip()
        for item in details
        if item.get("matched_shift")
    }

    checks = [
        (response_payload.get("summary", {}).get("total_logs"), expected_total_logs, "summary.total_logs"),
        (response_payload.get("summary", {}).get("checkins"), total_days, "summary.checkins"),
        (response_payload.get("summary", {}).get("checkouts"), total_days, "summary.checkouts"),
        (response_payload.get("summary", {}).get("unknown_events"), 0, "summary.unknown_events"),
        (compliance_summary.get("evaluated_employees"), 1, "compliance.summary.evaluated_employees"),
        (compliance_summary.get("expected_work_days"), total_days, "compliance.summary.expected_work_days"),
        (compliance_summary.get("compliant_days"), total_days, "compliance.summary.compliant_days"),
        (compliance_summary.get("partial_days"), 0, "compliance.summary.partial_days"),
        (compliance_summary.get("missing_days"), 0, "compliance.summary.missing_days"),
        (len(details), total_days, "compliance.employees[0].details.length"),
        (weekend_detail_count, expected_weekend_days, "compliance.employees[0].weekend_detail_count"),
    ]
    for actual, expected, label in checks:
        if actual != expected:
            raise RuntimeError(f"Rapport invalide sur {label}: attendu={expected}, recu={actual}")

    if employee_payload.get("person_id") != employee_no:
        raise RuntimeError("Rapport invalide: mauvais employee_no dans compliance.")
    if not used_shift_codes.issuperset(expected_shift_codes):
        raise RuntimeError(
            f"Rapport invalide: quarts utilises incomplets. Attendus={sorted(expected_shift_codes)}, recu={sorted(used_shift_codes)}"
        )
    if any((item.get("status") != "compliant") for item in details):
        raise RuntimeError("Rapport invalide: toutes les journees devraient etre conformes.")


@transaction.atomic
def run():
    args = parse_args()
    if args.month < 1 or args.month > 12:
        raise RuntimeError("Le mois doit etre compris entre 1 et 12.")

    target_year = args.year
    target_month = args.month
    month_start, month_end = month_bounds(target_year, target_month)
    tenant, _, device = ensure_tenant_gateway_and_device()
    cleanup_previous_simulation()

    shift_morning = WorkShift.objects.create(
        tenant=tenant,
        name="Simulation Quart 07h-14h",
        code=f"{SIM_PREFIX}-SHIFT-0714",
        start_time=time(7, 0),
        end_time=time(14, 0),
        overtime_minutes=120,
        metadata={"simulation": SIM_PREFIX},
    )
    shift_afternoon = WorkShift.objects.create(
        tenant=tenant,
        name="Simulation Quart 14h-22h",
        code=f"{SIM_PREFIX}-SHIFT-1422",
        start_time=time(14, 0),
        end_time=time(22, 0),
        overtime_minutes=180,
        metadata={"simulation": SIM_PREFIX},
    )
    shift_night = WorkShift.objects.create(
        tenant=tenant,
        name="Simulation Quart 22h-06h",
        code=f"{SIM_PREFIX}-SHIFT-2206",
        start_time=time(22, 0),
        end_time=time(6, 0),
        overtime_minutes=180,
        metadata={"simulation": SIM_PREFIX},
    )
    shifts_cycle = [shift_morning, shift_afternoon, shift_night]

    employee = ensure_employee(tenant, shifts_cycle)
    planning = build_complex_planning(
        tenant=tenant,
        month_start=month_start,
        shift_morning=shift_morning,
        shift_afternoon=shift_afternoon,
        shift_night=shift_night,
    )
    PlanningAssignment.objects.create(
        tenant=tenant,
        planning=planning,
        employee=employee,
        valid_from=month_start,
        flexible_weekend=True,
        priority=500,
        metadata={"simulation": SIM_PREFIX},
    )

    generation_stats = generate_monthly_logs(
        tenant=tenant,
        device=device,
        employee=employee,
        month_start=month_start,
        month_end=month_end,
        shifts_cycle=shifts_cycle,
    )

    report_user = ensure_report_user()
    request = APIRequestFactory().get(
        "/api/hikgateway/reports/attendance/",
        {
            "tenant": tenant.code,
            "period": "monthly",
            "start_date": month_start.isoformat(),
            "end_date": month_end.isoformat(),
            "person_ids": employee.employee_no,
        },
    )
    force_authenticate(request, user=report_user)
    response = hik_attendance_reports_api(request)
    if response.status_code != 200:
        raise RuntimeError(f"Echec generation rapport: {response.status_code} - {getattr(response, 'data', {})}")

    validate_report(
        response_payload=response.data,
        employee_no=employee.employee_no,
        month_start=month_start,
        month_end=month_end,
        expected_total_logs=generation_stats["total_logs"],
        expected_weekend_days=generation_stats["weekend_days"],
    )

    output_payload = {
        "simulation_context": {
            "simulation_prefix": SIM_PREFIX,
            "random_seed": RANDOM_SEED,
            "target_year": target_year,
            "target_month": target_month,
            "tenant": {"id": tenant.id, "code": tenant.code, "name": tenant.name},
            "employee": {"id": employee.id, "employee_no": employee.employee_no, "name": employee.full_name},
            "planning": {"id": planning.id, "code": planning.code, "name": planning.name},
            "month_range": {"start_date": month_start.isoformat(), "end_date": month_end.isoformat()},
            "generated_logs": generation_stats,
        },
        "report": response.data,
    }

    output_path = APP_DIR / "reports" / f"simulated_monthly_complex_attendance_report_{target_year}-{target_month:02d}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output_payload, ensure_ascii=False, indent=2, default=serialize_value),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "output_path": str(output_path),
                "tenant": tenant.code,
                "employee": employee.employee_no,
                "month": f"{target_year}-{target_month:02d}",
                "generated_logs": generation_stats["total_logs"],
                "weekend_days_covered": generation_stats["weekend_days"],
                "summary": response.data.get("summary", {}),
                "compliance_summary": (response.data.get("compliance", {}) or {}).get("summary", {}),
            },
            ensure_ascii=False,
            indent=2,
            default=serialize_value,
        )
    )


run()
