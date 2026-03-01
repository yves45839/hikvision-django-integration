import time

from django.core.management.base import BaseCommand, CommandError

from hik_gateway.services.device_dispatch import dispatch_hik_devices_to_core_devices
from hik_gateway.services.device_sync import sync_all_gateways


class Command(BaseCommand):
    help = "Sync Hikvision devices and maintain SN -> devIndex mapping"

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=0,
            help="Intervalle en secondes entre les synchronisations (0 = une seule exécution)",
        )
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Lance une synchronisation continue (arrêt avec CTRL+C)",
        )
        parser.add_argument(
            "--dispatch-core-devices",
            action="store_true",
            help="Recopie aussi les devices vers l'app devices (dispatch multi-tenant)",
        )

    def _run_once(self, *, dispatch: bool) -> tuple[int, int]:
        synced = sync_all_gateways()
        dispatched = dispatch_hik_devices_to_core_devices() if dispatch else 0
        return synced, dispatched

    def handle(self, *args, **options):
        interval = options["interval"]
        loop_forever = options["loop"]
        dispatch = options["dispatch_core_devices"]

        if interval < 0:
            raise CommandError("--interval doit être >= 0")

        if loop_forever and interval == 0:
            raise CommandError("--loop nécessite --interval > 0")

        if not loop_forever:
            synced, dispatched = self._run_once(dispatch=dispatch)
            suffix = f" | dispatched={dispatched}" if dispatch else ""
            self.stdout.write(self.style.SUCCESS(f"Synced {synced} devices{suffix}"))
            return

        self.stdout.write(self.style.WARNING(f"Continuous sync started (interval={interval}s)"))
        while True:
            synced, dispatched = self._run_once(dispatch=dispatch)
            suffix = f" | dispatched={dispatched}" if dispatch else ""
            self.stdout.write(self.style.SUCCESS(f"Synced {synced} devices{suffix}"))
            time.sleep(interval)
