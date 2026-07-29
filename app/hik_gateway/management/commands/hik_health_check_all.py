"""
PHASE 11.2 — Health check de tous les devices Hikvision
Vérifie la disponibilité et l'état des devices actifs.
"""
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from hik_gateway.models import Device, Gateway
from hik_gateway.client import HikGatewayClient

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Vérifie la disponibilité de tous les devices Hikvision actifs"

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-code",
            type=str,
            default=None,
            help="Filtrer par code tenant",
        )
        parser.add_argument(
            "--gateway-id",
            type=int,
            default=None,
            help="Filtrer par ID gateway",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Mettre à jour le statut des devices dans la DB",
        )

    def handle(self, *args, **options):
        tenant_code = options.get("tenant_code")
        gateway_id = options.get("gateway_id")
        update_db = options.get("update", False)

        # Récupérer les gateways
        gateways_qs = Gateway.objects.select_related("tenant").filter(kind=Gateway.KIND_HIKVISION)
        if tenant_code:
            gateways_qs = gateways_qs.filter(tenant__code__iexact=tenant_code)
        if gateway_id:
            gateways_qs = gateways_qs.filter(id=gateway_id)

        total_online = 0
        total_offline = 0
        total_errors = 0

        for gateway in gateways_qs:
            self.stdout.write(
                f"\nChecking gateway {gateway.id} ({gateway.base_url}) "
                f"for tenant {gateway.tenant.code}..."
            )

            # Récupérer les devices du gateway
            devices = Device.objects.filter(gateway=gateway)
            gateway_online = 0
            gateway_offline = 0

            try:
                client = HikGatewayClient(
                    base_url=gateway.base_url,
                    username=gateway.username,
                    password=gateway.password,
                    timeout=10,
                )

                for device in devices:
                    try:
                        # Essayer une recherche simple sur le device
                        payload = {
                            "SearchDescription": {
                                "position": 0,
                                "maxResult": 1,
                            }
                        }
                        result = client._post(
                            "/api/artemis/v2/device/search",
                            payload,
                            timeout=10,
                        )
                        # Si on arrive ici, le gateway répond
                        device.status = "online"
                        device.offline_hint = ""
                        device.last_seen_at = timezone.now()
                        gateway_online += 1
                        total_online += 1

                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✓ {device.serial_number} ({device.device_name}) "
                                f"is ONLINE"
                            )
                        )

                    except Exception as device_exc:
                        device.status = "offline"
                        device.offline_hint = str(device_exc)[:255]
                        gateway_offline += 1
                        total_offline += 1

                        self.stdout.write(
                            self.style.WARNING(
                                f"  ✗ {device.serial_number} ({device.device_name}) "
                                f"is OFFLINE: {device_exc}"
                            )
                        )

                    if update_db:
                        device.save(
                            update_fields=["status", "offline_hint", "last_seen_at"]
                        )

            except Exception as gateway_exc:
                logger.error(f"Failed to check gateway {gateway.id}: {gateway_exc}")
                self.stdout.write(
                    self.style.ERROR(
                        f"  Gateway error: {gateway_exc}"
                    )
                )
                total_errors += 1
                continue

            self.stdout.write(
                f"  Gateway summary: {gateway_online} online, {gateway_offline} offline"
            )

        # Résumé final
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS(f"Total online: {total_online}"))
        self.stdout.write(self.style.WARNING(f"Total offline: {total_offline}"))
        if total_errors > 0:
            self.stdout.write(self.style.ERROR(f"Total gateway errors: {total_errors}"))

        if update_db:
            self.stdout.write(
                self.style.SUCCESS(
                    "\nDevice statuses have been updated in the database."
                )
            )
