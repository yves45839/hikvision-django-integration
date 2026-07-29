"""Détection des rappels de pointage — scan par lots, sans N+1.

Fenêtres LARGES + journal d'idempotence (PunchReminderLog unique par
employé/date/type) : un redémarrage de beat rattrape les envois manqués au
lieu de les perdre, sans jamais envoyer deux fois.

Limites v1 (documentées) : seul le premier créneau de travail du jour est
rappelé (pas de reprise après pause ni de second shift) ; les shifts de nuit
sont avertis le jour de leur début.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone as dj_timezone

from employees.models import Employee
from employees.schedule_resolver import ScheduleResolver
from hik_gateway.models import AttendanceLog
from presence.models import PunchReminderLog, TenantNotificationSettings

logger = logging.getLogger(__name__)

# Fenêtre d'avance du resolver : un CHECK_IN jusqu'à 3 h avant l'heure prévue
# compte comme l'arrivée du shift (pas un pointage accidentel de la veille).
EARLY_CHECKIN_WINDOW = timedelta(minutes=180)


@dataclass
class ReminderCandidate:
    employee: Employee
    date: object  # date locale
    kind: str
    expected_start_at: datetime


def _warning_minutes() -> int:
    return int(getattr(settings, "PUNCH_WARNING_MINUTES", 15))


def _late_minutes() -> int:
    return int(getattr(settings, "PUNCH_LATE_MINUTES", 5))


def _late_cutoff_minutes() -> int:
    return int(getattr(settings, "PUNCH_LATE_CUTOFF_MINUTES", 60))


def run_reminder_scan(now_utc: datetime | None = None, *, dry_run: bool = False) -> dict:
    """Détecte et (sauf dry_run) crée+envoie les rappels dus à ``now_utc``.

    Chargement par lots : une requête employés, une réglages tenant, une
    CHECK_IN de la fenêtre, une rappels déjà envoyés. Les décisions par
    employé se font en mémoire (le resolver lit les relations préchargées).
    """
    from presence.notifications import dispatch_punch_reminder

    now_utc = now_utc or dj_timezone.now()
    resolver = ScheduleResolver()

    employees = list(
        Employee.objects.filter(is_active=True, user__isnull=False)
        .select_related("tenant", "planning", "work_shift", "department")
        .prefetch_related("work_shifts", "department__planning", "department__work_shift")
    )
    if not employees:
        return {"checked": 0, "due": 0, "sent": 0, "skipped_settings": 0}

    settings_by_tenant = {
        s.tenant_id: s
        for s in TenantNotificationSettings.objects.filter(
            tenant_id__in={e.tenant_id for e in employees}
        )
    }

    # CHECK_IN récents (fenêtre max : avance 3 h + cutoff), groupés par clé employé.
    window_start = now_utc - EARLY_CHECKIN_WINDOW - timedelta(minutes=_late_cutoff_minutes())
    employee_ids = {e.id for e in employees}
    person_ids = {e.employee_no for e in employees}
    checkins_by_employee: dict[int, list[datetime]] = {}
    checkins_by_person: dict[str, list[datetime]] = {}
    for employee_id, person_id, timestamp in AttendanceLog.objects.filter(
        timestamp__gte=window_start,
        normalized_action=AttendanceLog.ACTION_CHECK_IN,
    ).filter(Q(employee_id__in=employee_ids) | Q(person_id__in=person_ids)).values_list(
        "employee_id", "person_id", "timestamp"
    ):
        if employee_id:
            checkins_by_employee.setdefault(employee_id, []).append(timestamp)
        if person_id:
            checkins_by_person.setdefault(person_id, []).append(timestamp)

    already_sent = set(
        PunchReminderLog.objects.filter(
            date__gte=(now_utc - timedelta(days=2)).date()
        ).values_list("employee_id", "date", "kind")
    )

    stats = {"checked": 0, "due": 0, "sent": 0, "skipped_settings": 0}
    candidates: list[ReminderCandidate] = []

    for employee in employees:
        stats["checked"] += 1
        notif = settings_by_tenant.get(employee.tenant_id)
        reminders_on = notif.reminders_enabled if notif else True
        warning_on = notif.warning_enabled if notif else True
        late_on = notif.late_enabled if notif else True
        if not reminders_on:
            stats["skipped_settings"] += 1
            continue

        tz = resolver.resolve_employee_timezone(employee)
        local_now = now_utc.astimezone(tz)
        schedule = resolver.build_day_schedule(employee, local_now.date())
        if schedule.get("is_rest_day") or not schedule.get("has_work_period"):
            continue
        start_times = [
            slot["start_time"]
            for slot in schedule.get("slots", [])
            # Le resolver produit "work" (créneaux quotidiens) ou "shift"
            # (entrées liées à un quart) — les deux sont des périodes de travail.
            if slot.get("slot_type") in {"work", "shift"} and slot.get("start_time") is not None
        ]
        if not start_times:
            continue
        expected = datetime.combine(local_now.date(), min(start_times), tzinfo=tz)

        warning_due = (
            warning_on
            and expected - timedelta(minutes=_warning_minutes()) <= local_now < expected
        )
        late_due = (
            late_on
            and expected + timedelta(minutes=_late_minutes())
            <= local_now
            < expected + timedelta(minutes=_late_cutoff_minutes())
        )

        if late_due:
            # Un CHECK_IN dans [expected - 3 h, maintenant] masque le rappel ;
            # un pointage accidentel très matinal (hors fenêtre) ne le masque pas.
            checkins = checkins_by_employee.get(employee.id, []) + checkins_by_person.get(
                employee.employee_no, []
            )
            floor = expected - EARLY_CHECKIN_WINDOW
            if any(floor <= ts <= now_utc for ts in checkins):
                late_due = False

        for due, kind in ((warning_due, PunchReminderLog.KIND_PRE_START_WARNING),
                          (late_due, PunchReminderLog.KIND_LATE_REMINDER)):
            if not due:
                continue
            if (employee.id, local_now.date(), kind) in already_sent:
                continue
            stats["due"] += 1
            candidates.append(
                ReminderCandidate(
                    employee=employee, date=local_now.date(), kind=kind, expected_start_at=expected
                )
            )

    if dry_run:
        stats["candidates"] = [
            {"employee": c.employee.employee_no, "date": str(c.date), "kind": c.kind,
             "expected": c.expected_start_at.isoformat()}
            for c in candidates
        ]
        return stats

    for candidate in candidates:
        try:
            reminder, created = PunchReminderLog.objects.get_or_create(
                employee=candidate.employee,
                date=candidate.date,
                kind=candidate.kind,
                defaults={"expected_start_at": candidate.expected_start_at},
            )
        except IntegrityError:
            continue
        if not created:
            continue
        try:
            dispatch_punch_reminder(reminder)
            stats["sent"] += 1
        except Exception:
            logger.exception(
                "Dispatch du rappel échoué (employé %s, %s)", candidate.employee.id, candidate.kind
            )
    return stats
