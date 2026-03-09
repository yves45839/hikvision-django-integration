from django.conf import settings
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from hik_gateway.services.device_payload import extract_devices
from hik_gateway.services.gateway_connection import get_shared_gateway_client
from tenants.models import Tenant

from .models import Device
from .serializers import DeviceOnboardSerializer, DeviceSerializer


class DeviceViewSet(viewsets.ModelViewSet):

    def _build_http_host_payload(self):
        webhook_url = (getattr(settings, 'HIK_WEBHOOK_URL', '') or '').strip()
        webhook_ip = (getattr(settings, 'HIK_WEBHOOK_IP', '') or '').strip()
        webhook_port = int(getattr(settings, 'HIK_WEBHOOK_PORT', 443) or 443)

        if not webhook_url or not webhook_ip:
            return None

        return {
            'HttpHostNotification': {
                'id': 1,
                'url': webhook_url,
                'ipAddress': webhook_ip,
                'portNo': webhook_port,
                'protocolType': 'HTTP',
                'parameterFormatType': 'json',
                'addressingFormatType': 'ipaddress',
                'enable': True,
            }
        }

    queryset = Device.objects.none()
    serializer_class = DeviceSerializer

    def get_queryset(self):
        queryset = Device.objects.all().order_by('-id')
        owner_only = str(self.request.query_params.get('owner_only', '')).lower() in {'1', 'true', 'yes'}

        if owner_only and self.request.user.is_authenticated:
            return queryset.filter(owner=self.request.user)

        return queryset

    @action(detail=False, methods=['post'], url_path='onboard')
    def onboard(self, request):
        serializer = DeviceOnboardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        tenant = Tenant.objects.filter(code__iexact=validated['tenant_code']).first()
        if tenant is None:
            return Response({'detail': 'Tenant introuvable.'}, status=status.HTTP_400_BAD_REQUEST)

        sn = validated['sn']

        existing_device = Device.objects.filter(serial_number=sn).exclude(tenant=tenant).first()
        if existing_device:
            return Response(
                {'detail': 'Ce numéro de série est déjà affecté à un autre tenant.'},
                status=status.HTTP_409_CONFLICT,
            )

        device_for_tenant = Device.objects.filter(serial_number=sn, tenant=tenant).first()
        if device_for_tenant:
            output = DeviceSerializer(device_for_tenant)
            return Response(output.data, status=status.HTTP_200_OK)

        payload = {
            'DeviceInList': [{
                'Device': {
                    'protocolType': 'ehomeV5',
                    'EhomeParams': {
                        'EhomeID': sn,
                        'EhomeKey': validated['ehome_key'],
                    },
                    'devName': validated['dev_name'],
                    'devType': validated['dev_type'],
                }
            }]
        }

        try:
            gateway_client = get_shared_gateway_client(tenant_code=tenant.code)
            add_response = gateway_client.add_device(payload=payload)
        except Exception as exc:  # noqa: BLE001
            return Response({'detail': f"Échec d'ajout sur la gateway: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)

        device_out_list = add_response.get('DeviceOutList', {}) if isinstance(add_response, dict) else {}
        out_devices = device_out_list.get('Device', []) if isinstance(device_out_list, dict) else []
        if isinstance(out_devices, dict):
            out_devices = [out_devices]

        out_device = out_devices[0] if out_devices else {}
        add_status = str(out_device.get('status', '')).lower()
        sub_status_code = out_device.get('subStatusCode', '')

        if add_status not in {'', 'ok', 'success'} and sub_status_code != 'deviceExist':
            return Response(
                {
                    'detail': "La gateway a refusé l'ajout du device.",
                    'gateway_status': out_device,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        dev_index = out_device.get('devIndex') or ''

        if not dev_index:
            try:
                search_payload = gateway_client.device_list_all(
                    max_result=100,
                    protocol_types=['ehomeV5'],
                    dev_type=validated['dev_type'],
                    key=sn,
                )
            except Exception as exc:  # noqa: BLE001
                return Response(
                    {'detail': f"Ajout effectué mais impossible de récupérer devIndex: {exc}"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            for item in extract_devices(search_payload):
                ehome_params = item.get('EhomeParams', {}) if isinstance(item.get('EhomeParams'), dict) else {}
                if ehome_params.get('EhomeID') == sn:
                    dev_index = item.get('devIndex') or ''
                    if dev_index:
                        break

        if not dev_index:
            return Response(
                {'detail': "Ajout effectué mais devIndex introuvable pour ce device."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        webhook_payload = self._build_http_host_payload()
        if webhook_payload:
            try:
                gateway_client.set_http_host(dev_index=dev_index, payload=webhook_payload)
            except Exception:
                pass

        with transaction.atomic():
            device = Device.objects.create(
                owner=request.user,
                tenant=tenant,
                serial_number=sn,
                dev_index=dev_index,
                name=validated['dev_name'],
                protocol='ehomeV5',
                status='online',
                device_username=validated.get('device_username', ''),
                device_password=validated.get('device_password', ''),
            )

        output = DeviceSerializer(device)
        return Response(output.data, status=status.HTTP_201_CREATED)
