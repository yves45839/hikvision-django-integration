from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import OperationalError, ProgrammingError
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from employees.models import Employee, Planning, PlanningAssignment, PlanningEntry, PlanningPeriod, WorkShift


@dataclass
class ResolvedAssignment:
    assignment: PlanningAssignment | None
    source: str
    planning: Planning | None = None
    work_shift: WorkShift | None = None


@dataclass
class ResolvedShiftMatch:
    work_shift: WorkShift
    shift_date: date
    local_timestamp: datetime
    source: str


class ScheduleResolver:
    @staticmethod
    def _assignment_tables_available() -> bool:
        try:
            PlanningAssignment.objects.exists()
            return True
        except (OperationalError, ProgrammingError):
            return False

    @staticmethod
    def _planning_entry_table_available() -> bool:
        try:
            PlanningEntry.objects.exists()
            return True
        except (OperationalError, ProgrammingError):
            return False

    def resolve_effective_planning(self, employee: Employee, target_date: date | None = None) -> Planning | None:
        target_date = target_date or date.today()
        resolved = self.resolve_planning_assignment(employee, target_date)
        return resolved.planning

    def resolve_effective_work_shift(self, employee: Employee, target_date: date | None = None) -> WorkShift | None:
        target_date = target_date or date.today()
        resolved = self.resolve_work_shift_assignment(employee, target_date)
        return resolved.work_shift

    def resolve_effective_work_shifts(self, employee: Employee, target_date: date | None = None) -> list[WorkShift]:
        shifts = []
        seen = set()
        assigned_shift = self.resolve_effective_work_shift(employee, target_date)
        if assigned_shift is not None:
            shifts.append(assigned_shift)
            seen.add(assigned_shift.id)

        if employee.work_shift_id is not None:
            if employee.work_shift_id not in seen:
                shifts.append(employee.work_shift)
                seen.add(employee.work_shift_id)
        for current in employee.work_shifts.order_by("id"):
            if current.id not in seen:
                shifts.append(current)
                seen.add(current.id)
        if shifts:
            return shifts

        if employee.department_id is None:
            return []

        node = employee.department
        while node is not None:
            if node.work_shift_id and node.work_shift_id not in seen:
                shifts.append(node.work_shift)
                seen.add(node.work_shift_id)
                break
            node = node.parent
        return shifts

    def resolve_shift_from_timestamp(
        self,
        employee: Employee,
        event_dt: datetime,
        direction_hint: str | None = None,
    ) -> ResolvedShiftMatch | None:
        current_tz = self._resolve_employee_timezone(employee)
        local_event_dt = timezone.localtime(event_dt, current_tz)
        target_date = local_event_dt.date()
        candidate_shifts = self._resolve_shift_candidates_for_timestamp(
            employee=employee,
            target_date=target_date,
        )

        best_match = None
        best_score = None
        local_naive_dt = local_event_dt.replace(tzinfo=None)
        normalized_direction = str(direction_hint or "").strip().upper()
        early_checkin_window_minutes = 180

        for shift in candidate_shifts:
            start_time = shift.start_time
            end_time = shift.end_time
            if start_time is None or end_time is None:
                continue

            overtime_minutes = int(shift.overtime_minutes or 0)
            for shift_date in (target_date - timedelta(days=1), target_date):
                shift_start_naive = datetime.combine(shift_date, start_time)
                shift_end_naive = datetime.combine(shift_date, end_time)
                if shift_end_naive <= shift_start_naive:
                    shift_end_naive += timedelta(days=1)
                shift_overtime_end_naive = shift_end_naive + timedelta(minutes=overtime_minutes)
                shift_early_start_naive = shift_start_naive - timedelta(minutes=early_checkin_window_minutes)

                if normalized_direction == "OUT":
                    in_window = shift_start_naive <= local_naive_dt <= shift_overtime_end_naive
                    distance_score = abs(int((local_naive_dt - shift_end_naive).total_seconds() // 60))
                elif normalized_direction == "IN":
                    in_window = shift_early_start_naive <= local_naive_dt < shift_end_naive
                    distance_score = abs(int((local_naive_dt - shift_start_naive).total_seconds() // 60))
                else:
                    in_window = shift_start_naive <= local_naive_dt <= shift_overtime_end_naive
                    distance_score = abs(int((local_naive_dt - shift_start_naive).total_seconds() // 60))

                if not in_window:
                    continue

                tie_breaker = abs(int((local_naive_dt - shift_start_naive).total_seconds() // 60))
                score = (distance_score, tie_breaker, shift.id)
                if best_score is None or score < best_score:
                    best_score = score
                    best_match = ResolvedShiftMatch(
                        work_shift=shift,
                        shift_date=shift_date,
                        local_timestamp=local_event_dt,
                        source="effective_work_shifts",
                    )

        return best_match

    def _resolve_shift_candidates_for_timestamp(
        self,
        *,
        employee: Employee,
        target_date: date,
    ) -> list[WorkShift]:
        # Combine legacy/effective shifts and planning-derived shifts (target day + previous day)
        # so overnight events after midnight can be mapped to the previous shift day.
        candidates = []
        seen_ids = set()

        for shift in self.resolve_effective_work_shifts(employee, target_date=target_date):
            if shift.id in seen_ids:
                continue
            seen_ids.add(shift.id)
            candidates.append(shift)

        planning_shift_ids = set()
        for day in (target_date, target_date - timedelta(days=1)):
            day_schedule = self.build_day_schedule(employee, day)
            for shift_payload in day_schedule.get("shifts") or []:
                shift_id = shift_payload.get("id")
                if shift_id:
                    planning_shift_ids.add(int(shift_id))

        if planning_shift_ids:
            for shift in WorkShift.objects.filter(id__in=planning_shift_ids).order_by("id"):
                if shift.id in seen_ids:
                    continue
                seen_ids.add(shift.id)
                candidates.append(shift)

        return candidates

    def _resolve_employee_timezone(self, employee: Employee):
        planning = self.resolve_effective_planning(employee)
        timezone_name = str(getattr(planning, "timezone", "") or "").strip()
        if timezone_name:
            try:
                return ZoneInfo(timezone_name)
            except ZoneInfoNotFoundError:
                pass
        return timezone.get_current_timezone()

    def resolve_assignment(self, employee: Employee, target_date: date | None = None) -> dict:
        target_date = target_date or date.today()
        planning_assignment = self.resolve_planning_assignment(employee, target_date)
        work_shift_assignment = self.resolve_work_shift_assignment(employee, target_date)
        return {
            "planning": planning_assignment,
            "work_shift": work_shift_assignment,
        }

    def resolve_planning_assignment(self, employee: Employee, target_date: date) -> ResolvedAssignment:
        if self._assignment_tables_available():
            assignment = self._resolve_explicit_assignment(employee, target_date, field_name="planning")
            if assignment is not None:
                return ResolvedAssignment(assignment=assignment, source="assignment", planning=assignment.planning)

        if employee.planning_id is not None:
            return ResolvedAssignment(assignment=None, source="legacy_employee", planning=employee.planning)

        node = employee.department
        while node is not None:
            if node.planning_id is not None:
                source = "legacy_department" if node.id == employee.department_id else "legacy_department_inherited"
                return ResolvedAssignment(assignment=None, source=source, planning=node.planning)
            node = node.parent
        return ResolvedAssignment(assignment=None, source="none")

    def resolve_work_shift_assignment(self, employee: Employee, target_date: date) -> ResolvedAssignment:
        if self._assignment_tables_available():
            assignment = self._resolve_explicit_assignment(employee, target_date, field_name="work_shift")
            if assignment is not None:
                return ResolvedAssignment(assignment=assignment, source="assignment", work_shift=assignment.work_shift)

        if employee.work_shift_id is not None:
            return ResolvedAssignment(assignment=None, source="legacy_employee", work_shift=employee.work_shift)

        direct_shift = employee.work_shifts.order_by("id").first()
        if direct_shift is not None:
            return ResolvedAssignment(assignment=None, source="legacy_employee_multi", work_shift=direct_shift)

        node = employee.department
        while node is not None:
            if node.work_shift_id is not None:
                source = "legacy_department" if node.id == employee.department_id else "legacy_department_inherited"
                return ResolvedAssignment(assignment=None, source=source, work_shift=node.work_shift)
            node = node.parent
        return ResolvedAssignment(assignment=None, source="none")

    def build_day_schedule(self, employee: Employee, target_date: date) -> dict:
        planning_resolution = self.resolve_planning_assignment(employee, target_date)
        work_shift_resolution = self.resolve_work_shift_assignment(employee, target_date)
        planning = planning_resolution.planning
        fallback_shifts = self.resolve_effective_work_shifts(employee, target_date)

        if planning is not None:
            matched_entries = self._match_planning_entries(planning, target_date)
        else:
            matched_entries = []

        slots = []
        day_shifts = []
        planned_minutes = 0
        has_work_period = False
        is_rest_day = False

        if matched_entries:
            is_rest_day = True
            for entry in matched_entries:
                if entry.is_rest_day or entry.work_shift is None:
                    slots.append(
                        {
                            "id": entry.id,
                            "entry_id": entry.id,
                            "label": entry.label or "Repos",
                            "slot_type": "rest",
                            "start_time": None,
                            "end_time": None,
                            "duration_minutes": 0,
                        }
                    )
                    continue

                is_rest_day = False
                has_work_period = True
                shift_payload = self.serialize_work_shift(entry.work_shift)
                planned_minutes += shift_payload["total_minutes"]
                slots.append(
                    {
                        "id": entry.id,
                        "entry_id": entry.id,
                        "label": entry.label or entry.work_shift.name,
                        "slot_type": "shift",
                        "start_time": entry.work_shift.start_time,
                        "end_time": entry.work_shift.end_time,
                        "duration_minutes": shift_payload["total_minutes"],
                    }
                )
                day_shifts.append(shift_payload)
        elif planning is not None:
            slots, day_shifts, planned_minutes, has_work_period, is_rest_day = self._build_day_from_legacy_planning(
                planning=planning,
                target_date=target_date,
                fallback_shifts=fallback_shifts,
            )
        elif fallback_shifts:
            has_work_period = True
            for shift in fallback_shifts:
                shift_payload = self.serialize_work_shift(shift)
                planned_minutes += shift_payload["total_minutes"]
                day_shifts.append(shift_payload)
                slots.append(
                    {
                        "id": shift.id,
                        "label": shift.name,
                        "slot_type": "shift",
                        "start_time": shift.start_time,
                        "end_time": shift.end_time,
                        "duration_minutes": shift_payload["total_minutes"],
                    }
                )
        else:
            is_rest_day = True

        return {
            "date": target_date.isoformat(),
            "weekday": target_date.weekday(),
            "is_rest_day": is_rest_day,
            "has_work_period": has_work_period,
            "planned_minutes": planned_minutes,
            "slots": slots,
            "shifts": day_shifts,
            "planning_id": planning.id if planning is not None else None,
            "planning_assignment_id": planning_resolution.assignment.id if planning_resolution.assignment else None,
            "work_shift_assignment_id": work_shift_resolution.assignment.id if work_shift_resolution.assignment else None,
            "planning_source": planning_resolution.source,
            "work_shift_source": work_shift_resolution.source,
        }

    def build_month_schedule(self, employee: Employee, month_start: date) -> dict:
        last_day = monthrange(month_start.year, month_start.month)[1]
        month_end = month_start.replace(day=last_day)
        planning_resolution = self.resolve_planning_assignment(employee, month_start)
        work_shift_resolution = self.resolve_work_shift_assignment(employee, month_start)

        days = []
        total_planned_minutes = 0
        total_shift_minutes = 0
        working_days = 0
        rest_days = 0
        work_shift_ids = set()
        collected_shifts = []

        cursor = month_start
        while cursor <= month_end:
            day_payload = self.build_day_schedule(employee, cursor)
            days.append(day_payload)
            total_planned_minutes += day_payload["planned_minutes"]
            if day_payload["has_work_period"]:
                working_days += 1
            if day_payload["is_rest_day"]:
                rest_days += 1
            for shift_payload in day_payload["shifts"]:
                total_shift_minutes += shift_payload["total_minutes"]
                if shift_payload["id"] not in work_shift_ids:
                    work_shift_ids.add(shift_payload["id"])
                    collected_shifts.append(shift_payload)
            cursor += timedelta(days=1)

        return {
            "month": month_start.strftime("%Y-%m"),
            "employee": {
                "id": employee.id,
                "employee_no": employee.employee_no,
                "name": employee.full_name or employee.employee_no,
            },
            "planning": self._serialize_planning(planning_resolution.planning),
            "assignment": {
                "planning": self._serialize_assignment(planning_resolution.assignment),
                "work_shift": self._serialize_assignment(work_shift_resolution.assignment),
            },
            "work_shifts": collected_shifts,
            "summary": {
                "days_in_month": last_day,
                "working_days": working_days,
                "rest_days": rest_days,
                "planned_minutes": total_planned_minutes,
                "shift_minutes": total_shift_minutes,
            },
            "days": days,
        }

    def _resolve_explicit_assignment(self, employee: Employee, target_date: date, field_name: str) -> PlanningAssignment | None:
        employee_candidates = list(
            PlanningAssignment.objects.select_related("planning", "work_shift")
            .filter(
                tenant=employee.tenant,
                employee=employee,
                valid_from__lte=target_date,
            )
            .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=target_date))
            .exclude(**{f"{field_name}__isnull": True})
        )
        best_employee = self._pick_best_assignment(employee_candidates, department_depth=0, is_employee=True)
        if best_employee is not None:
            return best_employee

        if employee.department_id is None:
            return None

        department_chain = [employee.department, *employee.department.get_ancestors()]
        depth_map = {department.id: index for index, department in enumerate(department_chain)}
        department_candidates = []
        assignments = (
            PlanningAssignment.objects.select_related("planning", "work_shift", "department")
            .filter(
                tenant=employee.tenant,
                department_id__in=depth_map.keys(),
                valid_from__lte=target_date,
            )
            .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=target_date))
            .exclude(**{f"{field_name}__isnull": True})
        )
        for assignment in assignments:
            depth = depth_map.get(assignment.department_id, 999)
            if depth == 0 or assignment.include_sub_departments:
                department_candidates.append((assignment, depth))
        return self._pick_best_assignment_from_pairs(department_candidates)

    def _pick_best_assignment(self, assignments: list[PlanningAssignment], department_depth: int, is_employee: bool):
        pairs = [(assignment, department_depth) for assignment in assignments]
        if is_employee:
            return self._pick_best_assignment_from_pairs(pairs, employee_priority=True)
        return self._pick_best_assignment_from_pairs(pairs)

    @staticmethod
    def _pick_best_assignment_from_pairs(
        assignment_pairs: list[tuple[PlanningAssignment, int]],
        employee_priority: bool = False,
    ) -> PlanningAssignment | None:
        if not assignment_pairs:
            return None

        def score(item):
            assignment, depth = item
            return (
                1 if employee_priority else 0,
                1 if assignment.is_temporary else 0,
                assignment.priority,
                -depth,
                assignment.valid_from.toordinal(),
                assignment.id,
            )

        return max(assignment_pairs, key=score)[0]

    def _match_planning_entries(self, planning: Planning, target_date: date) -> list[PlanningEntry]:
        if not self._planning_entry_table_available():
            return []
        entries = list(
            planning.entries.select_related("work_shift").order_by(
                "start_date",
                "end_date",
                "day_of_week",
                "sequence_index",
                "id",
            )
        )
        matched = [
            entry
            for entry in entries
            if entry.start_date and entry.end_date and entry.start_date <= target_date <= entry.end_date
        ]
        if matched:
            return matched

        matched = [entry for entry in entries if entry.day_of_week == target_date.weekday()]
        if matched:
            return matched

        cycle_length = int(planning.metadata.get("cycle_length_days") or 0)
        anchor_date = parse_date(str(planning.metadata.get("cycle_anchor_date") or ""))
        if cycle_length > 0 and anchor_date is not None:
            delta = (target_date - anchor_date).days
            if delta >= 0:
                sequence_index = delta % cycle_length
                matched = [entry for entry in entries if entry.sequence_index == sequence_index]
                if matched:
                    return matched

        return []

    def _build_day_from_legacy_planning(
        self,
        planning: Planning,
        target_date: date,
        fallback_shifts: list[WorkShift],
    ) -> tuple[list[dict], list[dict], int, bool, bool]:
        slots = []
        day_shifts = []
        planned_minutes = 0
        has_work_period = False
        is_rest_day = False

        periods = list(planning.periods.prefetch_related("work_shifts").order_by("start_date", "end_date", "id"))
        matching_periods = [period for period in periods if period.start_date <= target_date <= period.end_date]
        if matching_periods:
            is_rest_day = True
            seen_shift_ids = set()
            for period in matching_periods:
                period_shifts = sorted(
                    period.work_shifts.all(),
                    key=lambda shift: (shift.start_time or time.min, shift.id),
                )
                if not period_shifts:
                    slots.append(
                        {
                            "id": period.id,
                            "period_id": period.id,
                            "label": period.label or "Repos",
                            "slot_type": "rest",
                            "start_time": None,
                            "end_time": None,
                            "duration_minutes": 0,
                        }
                    )
                    continue

                is_rest_day = False
                has_work_period = True
                for shift in period_shifts:
                    shift_payload = self.serialize_work_shift(shift)
                    planned_minutes += shift_payload["total_minutes"]
                    slots.append(
                        {
                            "id": shift.id,
                            "period_id": period.id,
                            "label": period.label or shift.name,
                            "slot_type": "shift",
                            "start_time": shift.start_time,
                            "end_time": shift.end_time,
                            "duration_minutes": shift_payload["total_minutes"],
                        }
                    )
                    if shift.id not in seen_shift_ids:
                        seen_shift_ids.add(shift.id)
                        day_shifts.append(shift_payload)
            return slots, day_shifts, planned_minutes, has_work_period, is_rest_day

        daily_slots = list(planning.daily_slots.filter(day_of_week=target_date.weekday()).order_by("start_time", "id"))
        if not daily_slots:
            return slots, day_shifts, planned_minutes, has_work_period, True

        seen_shift_ids = set()
        is_rest_day = True
        for slot in daily_slots:
            duration_minutes = self.duration_minutes(slot.start_time, slot.end_time)
            slots.append(
                {
                    "id": slot.id,
                    "label": slot.label,
                    "slot_type": slot.slot_type,
                    "start_time": slot.start_time,
                    "end_time": slot.end_time,
                    "duration_minutes": duration_minutes,
                }
            )
            if slot.slot_type == "rest":
                continue

            is_rest_day = False
            has_work_period = True
            planned_minutes += duration_minutes
            for shift in fallback_shifts:
                if shift.id in seen_shift_ids:
                    continue
                seen_shift_ids.add(shift.id)
                day_shifts.append(self.serialize_work_shift(shift))

        return slots, day_shifts, planned_minutes, has_work_period, is_rest_day

    @staticmethod
    def duration_minutes(start_time, end_time):
        if not start_time or not end_time:
            return 0
        start_dt = datetime.combine(date.today(), start_time)
        end_dt = datetime.combine(date.today(), end_time)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
        return int((end_dt - start_dt).total_seconds() // 60)

    @classmethod
    def serialize_work_shift(cls, shift: WorkShift) -> dict:
        total_minutes = cls.duration_minutes(shift.start_time, shift.end_time)
        break_minutes = cls.duration_minutes(shift.break_start_time, shift.break_end_time)
        net_minutes = max(total_minutes - break_minutes, 0)
        return {
            "id": shift.id,
            "name": shift.name,
            "code": shift.code,
            "description": shift.description,
            "start_time": shift.start_time,
            "end_time": shift.end_time,
            "break_start_time": shift.break_start_time,
            "break_end_time": shift.break_end_time,
            "overtime_minutes": shift.overtime_minutes,
            "total_minutes": total_minutes,
            "net_minutes": net_minutes,
        }

    @staticmethod
    def _serialize_planning(planning: Planning | None) -> dict | None:
        if planning is None:
            return None
        return {
            "id": planning.id,
            "tenant": planning.tenant_id,
            "name": planning.name,
            "code": planning.code,
            "timezone": planning.timezone,
        }

    @staticmethod
    def _serialize_assignment(assignment: PlanningAssignment | None) -> dict | None:
        if assignment is None:
            return None
        return {
            "id": assignment.id,
            "planning": assignment.planning_id,
            "work_shift": assignment.work_shift_id,
            "department": assignment.department_id,
            "employee": assignment.employee_id,
            "valid_from": assignment.valid_from,
            "valid_to": assignment.valid_to,
            "include_sub_departments": assignment.include_sub_departments,
            "priority": assignment.priority,
            "is_temporary": assignment.is_temporary,
        }
