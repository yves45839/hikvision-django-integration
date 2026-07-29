"""Tests de l'infrastructure Celery (Phase 0 pointage mobile)."""
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase


class CeleryAppTests(SimpleTestCase):
    def test_celery_app_importable_and_named(self):
        from config import celery_app

        self.assertEqual(celery_app.main, "config")

    def test_beat_schedule_declares_catchup(self):
        from django.conf import settings

        entry = settings.CELERY_BEAT_SCHEDULE["hik-catchup-every-minute"]
        self.assertEqual(entry["task"], "hik_gateway.tasks.hik_catchup_all")
        self.assertEqual(entry["schedule"], 60.0)

    def test_redis_db_url_helper(self):
        from config.settings import _redis_db_url

        self.assertEqual(_redis_db_url("redis://redis:6379", 1), "redis://redis:6379/1")
        self.assertEqual(_redis_db_url("redis://redis:6379/", 2), "redis://redis:6379/2")
        self.assertEqual(_redis_db_url("redis://redis:6379/5", 1), "redis://redis:6379/5")


class HikCatchupTaskTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_task_runs_management_command(self):
        from hik_gateway.tasks import hik_catchup_all

        with mock.patch("hik_gateway.tasks.call_command") as call_command:
            result = hik_catchup_all()
        call_command.assert_called_once_with("hik_catchup_acs_events")
        self.assertEqual(result, "ok")

    def test_lock_prevents_concurrent_run(self):
        from hik_gateway.tasks import CATCHUP_LOCK_KEY, hik_catchup_all

        cache.add(CATCHUP_LOCK_KEY, "1", timeout=30)
        with mock.patch("hik_gateway.tasks.call_command") as call_command:
            result = hik_catchup_all()
        call_command.assert_not_called()
        self.assertEqual(result, "skipped:locked")

    def test_lock_released_after_failure(self):
        from hik_gateway.tasks import CATCHUP_LOCK_KEY, hik_catchup_all

        with mock.patch("hik_gateway.tasks.call_command", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                hik_catchup_all()
        self.assertIsNone(cache.get(CATCHUP_LOCK_KEY))
