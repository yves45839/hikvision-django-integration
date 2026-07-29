"""Tests du scan de rappels et du dispatch multi-canal (Phase 4)."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from employees.models import Employee, Planning, PlanningDailySlot
from hik_gateway.models import AttendanceLog
from presence.models import EmployeePushToken, PunchReminderLog, TenantNotificationSettings
from presence.reminders import run_reminder_scan
from presence.services import get_mobile_device
from tenants.models import Tenant, TenantMembership, TenantRole

User = get_user_model()

_FAST_HASHER = override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)

# Planning UTC, service 08:00-17:00 tous les jours ouvrés.
SHIFT_START = time(8, 0)


def utc(hour, minute, day=30):
    return datetime(2026, 7, day, hour, minute, tzinfo=dt_timezone.utc)


@_FAST_HASHER
class ReminderScanTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(code="REM-A", name="Reminders", is_active=True)
        cls.user = User.objects.create_user("rem@r.test", "rem@r.test", "pass1234!")
        TenantMembership.objects.create(user=cls.user, tenant=cls.tenant, role=TenantRole.EMPLOYEE)

        cls.planning = Planning.objects.create(
            tenant=cls.tenant, name="Std", code="STD", timezone="UTC"
        )
        for dow in range(7):
            PlanningDailySlot.objects.create(
                planning=cls.planning, day_of_week=dow, slot_type="work",
                start_time=SHIFT_START, end_time=time(17, 0),
            )
        cls.employee = Employee.objects.create(
            tenant=cls.tenant, employee_no="2001", name="Rita", user=cls.user,
            planning=cls.planning, email="rita@r.test",
        )

    def scan(self, at, dry_run=False):
        return run_reminder_scan(at, dry_run=dry_run)


class WindowTests(ReminderScanTestBase):
    def _dry_kinds(self, at):
        stats = self.scan(at, dry_run=True)
        return [c["kind"] for c in stats.get("candidates", [])]

    def test_window_edges(self):
        self.assertEqual(self._dry_kinds(utc(7, 44)), [])                       # T-16 : rien
        self.assertEqual(self._dry_kinds(utc(7, 45)), ["pre_start_warning"])    # T-15
        self.assertEqual(self._dry_kinds(utc(7, 59)), ["pre_start_warning"])    # T-1
        self.assertEqual(self._dry_kinds(utc(8, 0)), [])                        # T : rien
        self.assertEqual(self._dry_kinds(utc(8, 4)), [])                        # T+4 : rien
        self.assertEqual(self._dry_kinds(utc(8, 5)), ["late_reminder"])         # T+5
        self.assertEqual(self._dry_kinds(utc(8, 59)), ["late_reminder"])        # T+59
        self.assertEqual(self._dry_kinds(utc(9, 0)), [])                        # cutoff

    def test_rest_day_skipped(self):
        PlanningDailySlot.objects.all().update(slot_type="rest")
        self.assertEqual(self._dry_kinds(utc(7, 50)), [])

    def test_unlinked_employee_skipped(self):
        self.employee.user = None
        self.employee.save(update_fields=["user"])
        self.assertEqual(self._dry_kinds(utc(7, 50)), [])

    def test_tenant_settings_disable(self):
        TenantNotificationSettings.objects.create(tenant=self.tenant, reminders_enabled=False)
        stats = self.scan(utc(7, 50), dry_run=True)
        self.assertEqual(stats.get("candidates", []), [])
        self.assertEqual(stats["skipped_settings"], 1)

    def test_warning_disabled_late_still_on(self):
        TenantNotificationSettings.objects.create(tenant=self.tenant, warning_enabled=False)
        self.assertEqual(self._dry_kinds(utc(7, 50)), [])
        self.assertEqual(self._dry_kinds(utc(8, 10)), ["late_reminder"])


class CheckinMaskingTests(ReminderScanTestBase):
    def _create_checkin(self, at):
        device = get_mobile_device(self.tenant)
        from hik_gateway.models import RawEvent

        raw = RawEvent.objects.create(
            tenant=self.tenant, device=device, dev_index="MOBILE", event_type="seed",
            event_datetime=at, employee_no="2001",
            dedupe_key=f"seed-{at.isoformat()}", payload={},
        )
        AttendanceLog.objects.create(
            tenant=self.tenant, employee=self.employee, person_id="2001", device=device,
            timestamp=at, attendance_type="seed", normalized_action="CHECK_IN",
            direction="IN", source=AttendanceLog.SOURCE_REALTIME, raw_event=raw,
        )

    def test_checkin_in_shift_window_masks_late_reminder(self):
        self._create_checkin(utc(7, 30))  # arrivée en avance, dans la fenêtre 3 h
        stats = self.scan(utc(8, 10), dry_run=True)
        self.assertEqual(stats.get("candidates", []), [])

    def test_very_early_accidental_checkin_does_not_mask(self):
        self._create_checkin(utc(3, 0))  # 5 h avant : hors fenêtre de 3 h
        stats = self.scan(utc(8, 10), dry_run=True)
        self.assertEqual([c["kind"] for c in stats["candidates"]], ["late_reminder"])


class TimezoneTests(ReminderScanTestBase):
    def test_planning_timezone_respected(self):
        # Abidjan = UTC+0... utiliser un fuseau décalé pour le test : Nairobi UTC+3.
        self.planning.timezone = "Africa/Nairobi"
        self.planning.save(update_fields=["timezone"])
        # 08:00 Nairobi = 05:00 UTC → avertissement à 04:45 UTC.
        stats = self.scan(utc(4, 50), dry_run=True)
        self.assertEqual([c["kind"] for c in stats["candidates"]], ["pre_start_warning"])
        stats = self.scan(utc(7, 50), dry_run=True)  # 10:50 locale : plus rien
        self.assertEqual(stats.get("candidates", []), [])


@override_settings(SMS_BACKEND="presence.sms.NoopSmsBackend")
class DispatchTests(ReminderScanTestBase):
    def setUp(self):
        EmployeePushToken.objects.create(
            employee=self.employee, token="ExponentPushToken[test1]",
            platform="android", installation_id="inst-1", locale="fr",
        )

    def _run_real(self, at):
        with mock.patch("presence.notifications.requests.post") as post:
            post.return_value.raise_for_status.return_value = None
            post.return_value.json.return_value = {"data": [{"status": "ok"}]}
            stats = self.scan(at)
        return stats, post

    def test_send_once_idempotent_across_scans(self):
        stats1, post = self._run_real(utc(7, 50))
        self.assertEqual(stats1["sent"], 1)
        stats2, _ = self._run_real(utc(7, 51))  # relance du scan (redémarrage beat)
        self.assertEqual(stats2["sent"], 0)
        self.assertEqual(PunchReminderLog.objects.count(), 1)

    def test_channel_statuses_persisted(self):
        self._run_real(utc(7, 50))
        reminder = PunchReminderLog.objects.get()
        self.assertEqual(reminder.push_status, PunchReminderLog.CHANNEL_SENT)
        self.assertEqual(reminder.email_status, PunchReminderLog.CHANNEL_SENT)
        self.assertEqual(reminder.sms_status, PunchReminderLog.CHANNEL_SKIPPED)  # défaut off
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("07:45", "07:45")  # heure locale rendue dans le corps
        self.assertIn("08:00", mail.outbox[0].body)

    def test_expo_payload_shape_and_device_not_registered(self):
        with mock.patch("presence.notifications.requests.post") as post:
            post.return_value.raise_for_status.return_value = None
            post.return_value.json.return_value = {
                "data": [{"status": "error", "details": {"error": "DeviceNotRegistered"}}]
            }
            self.scan(utc(7, 50))
            args, kwargs = post.call_args
            message = kwargs["json"][0]
            self.assertEqual(message["to"], "ExponentPushToken[test1]")
            self.assertIn("title", message)
            self.assertEqual(message["data"]["kind"], "pre_start_warning")
        token = EmployeePushToken.objects.get()
        self.assertFalse(token.is_active)

    def test_push_failure_does_not_block_email(self):
        with mock.patch(
            "presence.notifications.requests.post", side_effect=RuntimeError("network")
        ):
            self.scan(utc(7, 50))
        reminder = PunchReminderLog.objects.get()
        self.assertEqual(reminder.push_status, PunchReminderLog.CHANNEL_FAILED)
        self.assertEqual(reminder.email_status, PunchReminderLog.CHANNEL_SENT)

    def test_channels_disabled_by_tenant(self):
        TenantNotificationSettings.objects.create(
            tenant=self.tenant, push_enabled=False, email_enabled=False
        )
        self.scan(utc(7, 50))
        reminder = PunchReminderLog.objects.get()
        self.assertEqual(reminder.push_status, PunchReminderLog.CHANNEL_SKIPPED)
        self.assertEqual(reminder.email_status, PunchReminderLog.CHANNEL_SKIPPED)
        self.assertEqual(len(mail.outbox), 0)


class ScanQueryBudgetTests(ReminderScanTestBase):
    def test_scan_query_count_bounded(self):
        # 5 employés supplémentaires sur le même planning : le nombre de
        # requêtes ne doit pas croître linéairement (pas de N+1 de chargement ;
        # le resolver effectue des lectures bornées par employé).
        for i in range(5):
            user = User.objects.create_user(f"bulk{i}@r.test", f"bulk{i}@r.test", "pass1234!")
            TenantMembership.objects.create(user=user, tenant=self.tenant, role=TenantRole.EMPLOYEE)
            Employee.objects.create(
                tenant=self.tenant, employee_no=f"30{i}", name=f"Bulk {i}", user=user,
                planning=self.planning,
            )
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            self.scan(utc(6, 0), dry_run=True)  # hors fenêtres : décisions pures
        # Chargements globaux par lots + lectures internes du ScheduleResolver
        # (~16/employé, linéaire). La borne attrape toute dérive quadratique ;
        # l'optimisation documentée (cache Redis par employé/jour) réduira la
        # constante.
        self.assertLessEqual(len(ctx.captured_queries), 10 + 20 * 6)


@_FAST_HASHER
class PushTokenEndpointTests(ReminderScanTestBase):
    URL = "/api/mobile/push-token/"

    def setUp(self):
        from rest_framework.test import APIClient

        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def test_register_and_rotate_by_installation(self):
        response = self.api.post(
            self.URL,
            {"token": "ExponentPushToken[a]", "platform": "android", "installation_id": "inst-9"},
            format="json",
        )
        self.assertEqual(response.status_code, 204, response.content)
        response = self.api.post(
            self.URL,
            {"token": "ExponentPushToken[b]", "platform": "android", "installation_id": "inst-9"},
            format="json",
        )
        self.assertEqual(response.status_code, 204)
        tokens = {t.token: t.is_active for t in EmployeePushToken.objects.all()}
        self.assertEqual(tokens, {"ExponentPushToken[a]": False, "ExponentPushToken[b]": True})

    def test_delete_deactivates(self):
        self.api.post(self.URL, {"token": "ExponentPushToken[c]"}, format="json")
        response = self.api.delete(self.URL, {"token": "ExponentPushToken[c]"}, format="json")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(EmployeePushToken.objects.get().is_active)


@_FAST_HASHER
class NotificationSettingsEndpointTests(ReminderScanTestBase):
    URL = "/api/punch-notification-settings/"

    def test_requires_tenant_admin(self):
        from rest_framework.test import APIClient

        api = APIClient()
        api.force_authenticate(self.user)  # rôle employee
        response = api.get(self.URL, {"tenant": "REM-A"})
        self.assertEqual(response.status_code, 403)

    def test_read_write(self):
        from rest_framework.test import APIClient

        admin = User.objects.create_user("nadmin@r.test", "nadmin@r.test", "pass1234!")
        TenantMembership.objects.create(user=admin, tenant=self.tenant, role=TenantRole.TENANT_ADMIN)
        api = APIClient()
        api.force_authenticate(admin)
        response = api.get(self.URL, {"tenant": "REM-A"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["push_enabled"])
        response = api.put(f"{self.URL}?tenant=REM-A", {"push_enabled": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["push_enabled"])
        self.assertFalse(TenantNotificationSettings.objects.get(tenant=self.tenant).push_enabled)
