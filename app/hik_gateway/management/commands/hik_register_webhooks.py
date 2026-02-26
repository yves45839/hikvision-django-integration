from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from hik_gateway.client import HikGatewayClient
from hik_gateway.models import Device


class Command(BaseCommand):
    help = "Register HttpHostNotification webhook endpoint for each synced device"

    def add_arguments(self, parser):
        parser.add_argument("--ip-address", default=getattr(settings, "HIK_WEBHOOK_IP", ""))
        parser.add_argument("--port", type=int, default=getattr(settings, "HIK_WEBHOOK_PORT", 443))
        parser.add_argument("--url", default=getattr(settings, "HIK_WEBHOOK_URL", "/api/hik/events"))

    def handle(self, *args, **options):
        ip_address = options["ip_address"]
        port = options["port"]
        url = options["url"]

        if not ip_address:
            raise CommandError("ip-address is required (or set HIK_WEBHOOK_IP)")

        registered = 0
        for device in Device.objects.select_related("gateway").all().iterator():
            client = HikGatewayClient(
                device.gateway.base_url,
                device.gateway.username,
                device.gateway.password,
            )
            payload = {
                "HttpHostNotificationList": [
                    {
                        "HttpHostNotification": {
                            "id": "1",
                            "url": url,
                            "protocolType": "HTTP",
                            "addressingFormatType": "ipaddress",
                            "ipAddress": ip_address,
                            "portNo": port,
                            "SubscribeEvent": {
                                "heartbeat": 30,
                                "eventMode": "all",
                            },
                        }
                    }
                ]
            }
            client.set_http_host(device.dev_index, payload)
            registered += 1

        self.stdout.write(self.style.SUCCESS(f"Registered webhook for {registered} devices"))
