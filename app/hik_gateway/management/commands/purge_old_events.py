"""
PHASE 6.5 — Purge des événements ACS anciens selon la politique de rétention
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from hik_gateway.models import RawEvent, AttendanceLog


class Command(BaseCommand):
    help = "Purge les événements ACS anciens selon la politique de rétention"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Nombre de jours avant suppression (défaut: 90)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mode simulation sans supprimer",
        )
        parser.add_argument(
            "--event-type",
            type=str,
            choices=["raw", "attendance", "all"],
            default="all",
            help="Type d'événement à purger",
        )

    def handle(self, *args, **options):
        cutoff_date = timezone.now() - timedelta(days=options["days"])
        dry_run = options["dry_run"]
        event_type = options["event_type"]

        self.stdout.write(
            f"Purging events older than {options['days']} days "
            f"(before {cutoff_date.isoformat()})..."
        )

        total_deleted = 0

        # Purger les RawEvents
        if event_type in ["raw", "all"]:
            raw_events_qs = RawEvent.objects.filter(received_at__lt=cutoff_date)
            raw_count = raw_events_qs.count()

            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f"[DRY RUN] Would delete {raw_count} RawEvent records"
                    )
                )
            else:
                deleted, _ = raw_events_qs.delete()
                self.stdout.write(
                    self.style.SUCCESS(f"Deleted {deleted} RawEvent records")
                )
                total_deleted += deleted

        # Purger les AttendanceLogs
        if event_type in ["attendance", "all"]:
            attendance_logs_qs = AttendanceLog.objects.filter(created_at__lt=cutoff_date)
            attendance_count = attendance_logs_qs.count()

            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f"[DRY RUN] Would delete {attendance_count} AttendanceLog records"
                    )
                )
            else:
                deleted, _ = attendance_logs_qs.delete()
                self.stdout.write(
                    self.style.SUCCESS(f"Deleted {deleted} AttendanceLog records")
                )
                total_deleted += deleted

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] Total records to be deleted: ~{raw_count + attendance_count if event_type == 'all' else (raw_count if event_type == 'raw' else attendance_count)}"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Total deleted: {total_deleted} records")
            )
