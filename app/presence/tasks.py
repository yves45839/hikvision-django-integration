"""Tâches Celery du pointage mobile."""
import logging

from celery import shared_task
from django.core.cache import cache

logger = logging.getLogger(__name__)

REMINDER_LOCK_KEY = "lock:punch_reminders"


@shared_task(name="presence.tasks.check_punch_reminders")
def check_punch_reminders() -> dict:
    """Scan par minute des rappels de pointage (avertissement T-15,
    rappel T+5 si non pointé). Idempotent — voir presence.reminders."""
    if not cache.add(REMINDER_LOCK_KEY, "1", timeout=55):
        return {"skipped": "locked"}
    try:
        from presence.reminders import run_reminder_scan

        stats = run_reminder_scan()
        if stats.get("sent"):
            logger.info("Rappels de pointage envoyés: %s", stats)
        return stats
    finally:
        cache.delete(REMINDER_LOCK_KEY)
