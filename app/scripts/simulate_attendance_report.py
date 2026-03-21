import json
import os
import sys
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
from hik_gateway.models import AttendanceLog, RawEvent
from hik_gateway.views import hik_attendance_reports_api
from tenants.models import Tenant


SIM_PREFIX = "SIM-TEST-ATTENDANCE"
ANCHOR_DATE = date(2026, 3, 9)
REPORT_START = date(2026, 3, 9)
REPORT_END = date(2026, 3, 20)


def make_local_dt(target_day: date, hh: int, mm: int = 0, day_offset: int = 0):
    tz = timezone.get_current_timezone()
    value = datetime.combine(target_day + timedelta(days=day_offset), time(hh, mm))
    return timezone.make_aware(value, tz)


def serialize_value(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, set):
        return sorted(list(value))
    return str(value)


def cleanup_previous_simulation():
    AttendanceLog.objects.filter(raw_event__dedupe_key__startswith=f"{SIM_PREFIX}:").delete()
    RawEvent.objects.filter(dedupe_key__startswith=f"{SIM_PREFIX}:").delete()
    PlanningAssignment.objects.filter(metadata__simulation=SIM_PREFIX).delete()
    PlanningEntry.objects.filter(planning__code__startswith=SIM_PREFIX).delete()
    Planning.objects.filter(code__startswith=SIM_PREFIX).delete()
    WorkShift.objects.filter(code__startswith=SIM_PREFIX).delete()


def ensure_report_user():
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="sim_report_admin",
        defaults={
            "email": "sim_report_admin@example.local",
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


def create_attendance_log(*, tenant, device, employee, event_dt, direction, attendance_type, action):
    person_id = employee.employee_no
    dedupe_key = f"{SIM_PREFIX}:{person_id}:{event_dt.isoformat()}:{direction}:{uuid4().hex[:8]}"
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
        employee_no=person_id,
        employee_no_string=person_id,
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
        person_id=person_id,
        device=device,
        timestamp=event_dt,
        attendance_type=attendance_type,
        attendance_status=attendance_type,
        normalized_action=action,
        direction=direction,
        source=AttendanceLog.SOURCE_REALTIME,
        raw_event=raw,
    )


def simulate_for_office_employee(tenant, device, employee, office_shift):
    planning = Planning.objects.create(
        tenant=tenant,
        name="Simulation Lundi-Vendredi 08h-17h",
        code=f"{SIM_PREFIX}-OFFICE-PLANNING",
        description="Scenario de test L-V 08:00-17:00",
        timezone=str(timezone.get_current_timezone()),
        metadata={"simulation": SIM_PREFIX},
    )
    for day_of_week in range(0, 5):
        PlanningEntry.objects.create(
            planning=planning,
            day_of_week=day_of_week,
            work_shift=office_shift,
            label="Journee bureau",
            metadata={"simulation": SIM_PREFIX},
        )

    PlanningAssignment.objects.create(
        tenant=tenant,
        planning=planning,
        employee=employee,
        valid_from=REPORT_START,
        priority=100,
        metadata={"simulation": SIM_PREFIX},
    )

    week_days = [
        REPORT_START,  # 2026-03-09
        REPORT_START + timedelta(days=1),
        REPORT_START + timedelta(days=2),
        REPORT_START + timedelta(days=3),
        REPORT_START + timedelta(days=4),
    ]
    # Arrivee/Depart/Pause avec variation de retard et heure sup.
    patterns = [
        {"in": (8, 3), "break_out": (12, 2), "break_in": (13, 0), "out": (17, 8)},
        {"in": (7, 58), "break_out": (12, 0), "break_in": (13, 1), "out": (17, 2)},
        {"in": (8, 17), "break_out": (12, 6), "break_in": (13, 10), "out": (17, 0)},
        {"in": (8, 0), "break_out": (12, 4), "break_in": (13, 2), "out": None},
        {"in": (8, 1), "break_out": (12, 1), "break_in": (13, 0), "out": (19, 0)},
    ]

    for day, pattern in zip(week_days, patterns):
        create_attendance_log(
            tenant=tenant,
            device=device,
            employee=employee,
            event_dt=make_local_dt(day, *pattern["in"]),
            direction="IN",
            attendance_type="checkin",
            action=AttendanceLog.ACTION_CHECK_IN,
        )
        create_attendance_log(
            tenant=tenant,
            device=device,
            employee=employee,
            event_dt=make_local_dt(day, *pattern["break_out"]),
            direction="OUT",
            attendance_type="breakout",
            action=AttendanceLog.ACTION_BREAK_OUT,
        )
        create_attendance_log(
            tenant=tenant,
            device=device,
            employee=employee,
            event_dt=make_local_dt(day, *pattern["break_in"]),
            direction="IN",
            attendance_type="breakin",
            action=AttendanceLog.ACTION_BREAK_IN,
        )
        if pattern["out"] is not None:
            create_attendance_log(
                tenant=tenant,
                device=device,
                employee=employee,
                event_dt=make_local_dt(day, *pattern["out"]),
                direction="OUT",
                attendance_type="checkout",
                action=AttendanceLog.ACTION_CHECK_OUT,
            )

    return planning


def simulate_for_rotating_employee(tenant, device, employee, shift_a, shift_b, shift_c):
    planning = Planning.objects.create(
        tenant=tenant,
        name="Simulation 3 Quarts Tournants (3 jours)",
        code=f"{SIM_PREFIX}-ROTATION-PLANNING",
        description="Cycle A/B/C, rotation tous les 3 jours",
        timezone=str(timezone.get_current_timezone()),
        metadata={
            "simulation": SIM_PREFIX,
            "cycle_length_days": 9,
            "cycle_anchor_date": ANCHOR_DATE.isoformat(),
        },
    )

    for sequence_index in [0, 1, 2]:
        PlanningEntry.objects.create(
            planning=planning,
            sequence_index=sequence_index,
            work_shift=shift_a,
            label="Rotation A (06h-14h)",
            metadata={"simulation": SIM_PREFIX},
        )
    for sequence_index in [3, 4, 5]:
        PlanningEntry.objects.create(
            planning=planning,
            sequence_index=sequence_index,
            work_shift=shift_b,
            label="Rotation B (14h-22h)",
            metadata={"simulation": SIM_PREFIX},
        )
    for sequence_index in [6, 7, 8]:
        PlanningEntry.objects.create(
            planning=planning,
            sequence_index=sequence_index,
            work_shift=shift_c,
            label="Rotation C (22h-06h)",
            metadata={"simulation": SIM_PREFIX},
        )

    PlanningAssignment.objects.create(
        tenant=tenant,
        planning=planning,
        employee=employee,
        valid_from=REPORT_START,
        priority=99,
        metadata={"simulation": SIM_PREFIX},
    )

    # J1..J3 - Shift A (06h-14h)
    for offset, day_pattern in enumerate(
        [
            {"in": (5, 55), "break_out": (10, 0), "break_in": (10, 30), "out": (14, 12)},
            {"in": (6, 7), "break_out": (10, 4), "break_in": (10, 32), "out": (14, 5)},
            {"in": (6, 0), "break_out": (10, 10), "break_in": (10, 40), "out": (15, 30)},  # heure sup
        ]
    ):
        day = ANCHOR_DATE + timedelta(days=offset)
        create_attendance_log(tenant=tenant, device=device, employee=employee, event_dt=make_local_dt(day, *day_pattern["in"]), direction="IN", attendance_type="checkin", action=AttendanceLog.ACTION_CHECK_IN)
        create_attendance_log(tenant=tenant, device=device, employee=employee, event_dt=make_local_dt(day, *day_pattern["break_out"]), direction="OUT", attendance_type="breakout", action=AttendanceLog.ACTION_BREAK_OUT)
        create_attendance_log(tenant=tenant, device=device, employee=employee, event_dt=make_local_dt(day, *day_pattern["break_in"]), direction="IN", attendance_type="breakin", action=AttendanceLog.ACTION_BREAK_IN)
        create_attendance_log(tenant=tenant, device=device, employee=employee, event_dt=make_local_dt(day, *day_pattern["out"]), direction="OUT", attendance_type="checkout", action=AttendanceLog.ACTION_CHECK_OUT)

    # J4..J6 - Shift B (14h-22h), J5 volontairement incomplet (pas de checkout).
    for offset, day_pattern in enumerate(
        [
            {"in": (13, 55), "break_out": (18, 0), "break_in": (18, 30), "out": (22, 0)},
            {"in": (14, 5), "break_out": (18, 2), "break_in": (18, 30), "out": None},
            {"in": (14, 0), "break_out": (18, 0), "break_in": (18, 31), "out": (23, 15)},  # heure sup
        ]
    ):
        day = ANCHOR_DATE + timedelta(days=3 + offset)
        create_attendance_log(tenant=tenant, device=device, employee=employee, event_dt=make_local_dt(day, *day_pattern["in"]), direction="IN", attendance_type="checkin", action=AttendanceLog.ACTION_CHECK_IN)
        create_attendance_log(tenant=tenant, device=device, employee=employee, event_dt=make_local_dt(day, *day_pattern["break_out"]), direction="OUT", attendance_type="breakout", action=AttendanceLog.ACTION_BREAK_OUT)
        create_attendance_log(tenant=tenant, device=device, employee=employee, event_dt=make_local_dt(day, *day_pattern["break_in"]), direction="IN", attendance_type="breakin", action=AttendanceLog.ACTION_BREAK_IN)
        if day_pattern["out"] is not None:
            create_attendance_log(tenant=tenant, device=device, employee=employee, event_dt=make_local_dt(day, *day_pattern["out"]), direction="OUT", attendance_type="checkout", action=AttendanceLog.ACTION_CHECK_OUT)

    # J7..J9 - Shift C (22h-06h), sortie le lendemain.
    for offset, day_pattern in enumerate(
        [
            {"in": (22, 0), "break_out": (2, 0), "break_in": (2, 30), "out": (6, 10)},
            {"in": (22, 12), "break_out": (2, 5), "break_in": (2, 35), "out": (6, 0)},
            {"in": (21, 58), "break_out": (2, 0), "break_in": (2, 31), "out": (7, 15)},  # heure sup
        ]
    ):
        day = ANCHOR_DATE + timedelta(days=6 + offset)
        create_attendance_log(
            tenant=tenant,
            device=device,
            employee=employee,
            event_dt=make_local_dt(day, *day_pattern["in"]),
            direction="IN",
            attendance_type="checkin",
            action=AttendanceLog.ACTION_CHECK_IN,
        )
        create_attendance_log(
            tenant=tenant,
            device=device,
            employee=employee,
            event_dt=make_local_dt(day, *day_pattern["break_out"], day_offset=1),
            direction="OUT",
            attendance_type="breakout",
            action=AttendanceLog.ACTION_BREAK_OUT,
        )
        create_attendance_log(
            tenant=tenant,
            device=device,
            employee=employee,
            event_dt=make_local_dt(day, *day_pattern["break_in"], day_offset=1),
            direction="IN",
            attendance_type="breakin",
            action=AttendanceLog.ACTION_BREAK_IN,
        )
        create_attendance_log(
            tenant=tenant,
            device=device,
            employee=employee,
            event_dt=make_local_dt(day, *day_pattern["out"], day_offset=1),
            direction="OUT",
            attendance_type="checkout",
            action=AttendanceLog.ACTION_CHECK_OUT,
        )

    return planning


@transaction.atomic
def run():
    tenant = Tenant.objects.order_by("id").first()
    if tenant is None:
        raise RuntimeError("Aucun tenant trouve.")

    employees = list(
        Employee.objects.filter(tenant=tenant, is_active=True)
        .select_related("department")
        .order_by("id")[:2]
    )
    if len(employees) < 2:
        raise RuntimeError("Il faut au moins 2 employes actifs existants pour la simulation.")

    office_employee, rotating_employee = employees[0], employees[1]
    device = tenant.hik_devices.order_by("id").first()
    if device is None:
        raise RuntimeError("Aucun device Hik lie au tenant pour enregistrer les pointages.")

    cleanup_previous_simulation()

    office_shift = WorkShift.objects.create(
        tenant=tenant,
        name="Simulation Bureau 08h-17h",
        code=f"{SIM_PREFIX}-SHIFT-OFFICE",
        start_time=time(8, 0),
        end_time=time(17, 0),
        break_start_time=time(12, 0),
        break_end_time=time(13, 0),
        overtime_minutes=120,
        metadata={"simulation": SIM_PREFIX},
    )
    shift_a = WorkShift.objects.create(
        tenant=tenant,
        name="Simulation Quart A 06h-14h",
        code=f"{SIM_PREFIX}-SHIFT-A",
        start_time=time(6, 0),
        end_time=time(14, 0),
        break_start_time=time(10, 0),
        break_end_time=time(10, 30),
        overtime_minutes=120,
        metadata={"simulation": SIM_PREFIX},
    )
    shift_b = WorkShift.objects.create(
        tenant=tenant,
        name="Simulation Quart B 14h-22h",
        code=f"{SIM_PREFIX}-SHIFT-B",
        start_time=time(14, 0),
        end_time=time(22, 0),
        break_start_time=time(18, 0),
        break_end_time=time(18, 30),
        overtime_minutes=180,
        metadata={"simulation": SIM_PREFIX},
    )
    shift_c = WorkShift.objects.create(
        tenant=tenant,
        name="Simulation Quart C 22h-06h",
        code=f"{SIM_PREFIX}-SHIFT-C",
        start_time=time(22, 0),
        end_time=time(6, 0),
        break_start_time=time(2, 0),
        break_end_time=time(2, 30),
        overtime_minutes=180,
        metadata={"simulation": SIM_PREFIX},
    )

    office_planning = simulate_for_office_employee(tenant, device, office_employee, office_shift)
    rotating_planning = simulate_for_rotating_employee(tenant, device, rotating_employee, shift_a, shift_b, shift_c)

    report_user = ensure_report_user()
    request = APIRequestFactory().get(
        "/api/hikgateway/reports/attendance/",
        {
            "tenant": tenant.code,
            "period": "monthly",
            "start_date": REPORT_START.isoformat(),
            "end_date": REPORT_END.isoformat(),
            "person_ids": ",".join([office_employee.employee_no, rotating_employee.employee_no]),
        },
    )
    force_authenticate(request, user=report_user)
    response = hik_attendance_reports_api(request)
    if response.status_code != 200:
        raise RuntimeError(f"Echec generation rapport: {response.status_code} - {getattr(response, 'data', {})}")

    output = {
        "simulation_context": {
            "tenant": {"id": tenant.id, "code": tenant.code, "name": tenant.name},
            "employees": [
                {"id": office_employee.id, "employee_no": office_employee.employee_no, "name": office_employee.full_name},
                {"id": rotating_employee.id, "employee_no": rotating_employee.employee_no, "name": rotating_employee.full_name},
            ],
            "plannings": [
                {"id": office_planning.id, "code": office_planning.code, "name": office_planning.name},
                {"id": rotating_planning.id, "code": rotating_planning.code, "name": rotating_planning.name},
            ],
            "report_range": {"start_date": REPORT_START.isoformat(), "end_date": REPORT_END.isoformat()},
        },
        "report": response.data,
    }

    output_path = Path(__file__).resolve().parents[1] / "reports" / "simulated_attendance_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, default=serialize_value),
        encoding="utf-8",
    )

    print(json.dumps(
        {
            "status": "ok",
            "output_path": str(output_path),
            "tenant": tenant.code,
            "employees": [office_employee.employee_no, rotating_employee.employee_no],
            "report_period": [REPORT_START.isoformat(), REPORT_END.isoformat()],
            "report_summary": response.data.get("summary", {}),
            "compliance_summary": response.data.get("compliance", {}).get("summary", {}),
        },
        ensure_ascii=False,
        indent=2,
        default=serialize_value,
    ))


run()
