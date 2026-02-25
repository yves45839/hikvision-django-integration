from django.core.management.base import BaseCommand

from hik_gateway.services.device_sync import sync_all_gateways


class Command(BaseCommand):
    help = "Sync Hikvision devices and maintain SN -> devIndex mapping"

    def handle(self, *args, **options):
        total = sync_all_gateways()
        self.stdout.write(self.style.SUCCESS(f"Synced {total} devices"))
