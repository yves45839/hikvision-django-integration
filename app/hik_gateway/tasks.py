"""Tâches Celery de la passerelle Hikvision."""
import logging

from celery import shared_task
from django.core.cache import cache
from django.core.management import call_command

logger = logging.getLogger(__name__)

CATCHUP_LOCK_KEY = "lock:hik_catchup"
CATCHUP_LOCK_TTL_SECONDS = 55


@shared_task(name="hik_gateway.tasks.hik_catchup_all")
def hik_catchup_all() -> str:
    """Rattrapage périodique des événements ACS (remplace la boucle shell du
    compose de prod). Verrou cache : une seule exécution simultanée, y compris
    avec plusieurs workers."""
    if not cache.add(CATCHUP_LOCK_KEY, "1", timeout=CATCHUP_LOCK_TTL_SECONDS):
        return "skipped:locked"
    try:
        call_command("hik_catchup_acs_events")
        return "ok"
    except Exception:
        logger.exception("hik_catchup_all failed")
        raise
    finally:
        cache.delete(CATCHUP_LOCK_KEY)
