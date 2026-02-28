from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from hik_gateway.client import HikGatewayClient
from hik_gateway.models import Gateway
from hik_gateway.services.device_payload import extract_devices, normalize_device


class Command(BaseCommand):
    help = "Vérifie qu'un device déjà ajouté est visible depuis son gateway"

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Code tenant (ex: tenant-a)")
        parser.add_argument("--serial", help="Serial number du device")
        parser.add_argument("--dev-index", help="devIndex du device")

    def handle(self, *args, **options):
        serial = (options.get("serial") or "").strip()
        dev_index = (options.get("dev_index") or "").strip()
        tenant_code = options["tenant"].strip()

        if not serial and not dev_index:
            raise CommandError("Tu dois fournir --serial ou --dev-index")

        gateway = (
            Gateway.objects.select_related("tenant")
            .filter(tenant__code=tenant_code)
            .order_by("id")
            .first()
        )
        if gateway is None:
            raise CommandError(f"Aucune gateway trouvée pour le tenant '{tenant_code}'")

        client = HikGatewayClient(gateway.base_url, gateway.username, gateway.password)
        payload = client.device_list()
        devices = extract_devices(payload)

        match = None
        for item in devices:
            normalized = normalize_device(item)
            item_serial = str(normalized["serial_number"] or "").strip()
            item_dev_index = str(normalized["dev_index"] or "").strip()

            serial_ok = not serial or item_serial == serial
            dev_index_ok = not dev_index or item_dev_index == dev_index
            if serial_ok and dev_index_ok:
                match = item
                break

        if match is None:
            lookup = f"serial={serial or '-'} devIndex={dev_index or '-'}"
            raise CommandError(
                f"Device introuvable sur la gateway du tenant '{tenant_code}' ({lookup})"
            )

        resolved = normalize_device(match)
        resolved_serial = resolved["serial_number"]
        resolved_dev_index = resolved["dev_index"]
        status = resolved["status"] or "unknown"

        self.stdout.write(
            self.style.SUCCESS(
                "Communication OK ✅ "
                f"tenant={tenant_code} serial={resolved_serial} "
                f"devIndex={resolved_dev_index} status={status}"
            )
        )
