from django.core.management.base import BaseCommand

from hik_gateway.services.catchup import catchup_all_devices


class Command(BaseCommand):
    help = "Catch up missed access control events from /ISAPI/AccessControl/AcsEvent"

    def add_arguments(self, parser):
        parser.add_argument("--max-results", type=int, default=50)

    def handle(self, *args, **options):
        total = catchup_all_devices(max_results=options["max_results"])
        self.stdout.write(self.style.SUCCESS(f"Processed {total} catchup events"))
