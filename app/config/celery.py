"""Application Celery du projet.

Broker/backend configurés via les réglages Django (namespace CELERY_*).
Les tâches périodiques sont déclarées statiquement dans
``settings.CELERY_BEAT_SCHEDULE`` — pas de django-celery-beat.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
