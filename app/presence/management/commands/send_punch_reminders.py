"""Test manuel des rappels de pointage sans attendre l'heure réelle.

Exemples :
    python manage.py send_punch_reminders --at 2026-07-30T07:46:00+00:00 --dry-run
    python manage.py send_punch_reminders --at 2026-07-30T08:06:00+00:00
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from presence.reminders import run_reminder_scan


class Command(BaseCommand):
    help = "Exécute le scan des rappels de pointage (optionnellement à une heure simulée)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--at",
            help="Heure UTC simulée (ISO 8601, ex. 2026-07-30T07:46:00+00:00). Défaut : maintenant.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Liste les rappels dus sans rien créer ni envoyer.",
        )

    def handle(self, *args, **options):
        now_utc = None
        if options.get("at"):
            now_utc = parse_datetime(options["at"])
            if now_utc is None or now_utc.tzinfo is None:
                raise CommandError("--at doit être un datetime ISO 8601 avec fuseau.")
        stats = run_reminder_scan(now_utc, dry_run=options["dry_run"])
        self.stdout.write(json.dumps(stats, indent=2, default=str))
