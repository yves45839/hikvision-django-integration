from django.conf import settings
from django.db import transaction
from django.http import HttpResponseRedirect
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from urllib.parse import quote, urlparse
import ipaddress
import re

from employees.models import Employee, Organization
from employees.services import build_card_info_payloads, build_user_info_payload
from hik_gateway.services.device_payload import extract_devices
from hik_gateway.services.gateway_connection import get_shared_gateway_client
from tenants.models import Tenant, TenantMembership, TenantRole
from tenants.services import has_organization_role, has_tenant_role

from .models import Device, DeviceOnboardingJob
from .serializers import (
    DeviceOnboardSerializer,
    DeviceOnboardingJobCreateSerializer,
    DeviceOnboardingJobSerializer,
    DeviceSerializer,
)
from .services.onboarding import create_job, process_job, schedule_job


class DeviceViewSet(viewsets.ModelViewSet):
    _DEFAULT_GATEWAY_PLACEHOLDER_IP = '213.156.133.202'
    _HOST_KEYS = (
        'ipAddress',
        'ipv4Address',
        'ipv6Address',
        'devAddress',
        'devIp',
        'manageAddress',
        'hostAddress',
        'hostName',
        'host',
        'address',
    )
    _PORT_KEYS = (
        'httpPort',
        'webPort',
        'portNo',
        'port',
        'managePort',
    )

    def _is_valid_host(self, value: str) -> bool:
        if not value:
            return False
        lowered = value.strip().lower()
        if lowered in {'localhost'}:
            return True
        try:
            ipaddress.ip_address(lowered)
            return True
        except ValueError:
            return bool(re.fullmatch(r'[a-z0-9.-]+', lowered))

    def _extract_host_and_port(self, payload: dict) -> tuple[str, int | None]:
        if not isinstance(payload, dict):
            return '', None

        host = ''
        port = None

        def _walk(node):
            nonlocal host, port
            if isinstance(node, dict):
                for key, value in node.items():
                    if not host and key in self._HOST_KEYS and isinstance(value, str):
                        parsed = urlparse(value if '://' in value else f'//{value}')
                        candidate_host = parsed.hostname or value.strip()
                        if self._is_valid_host(candidate_host):
                            host = candidate_host
                    if port is None and key in self._PORT_KEYS:
                        try:
                            candidate_port = int(value)
                            if 1 <= candidate_port <= 65535:
                                port = candidate_port
                        except (TypeError, ValueError):
                            pass

                    if host and port is not None:
                        return
                    _walk(value)
                    if host and port is not None:
                        return
            elif isinstance(node, list):
                for item in node:
                    _walk(item)
                    if host and port is not None:
                        return

        _walk(payload)
        return host, port

    def _build_device_config_url(self, request, device: Device) -> tuple[str, str]:
        host = ''
        port = None
        source = 'device_record'

        manual_host = str(request.query_params.get('host', '')).strip()
        if manual_host:
            if not self._is_valid_host(manual_host):
                raise ValueError('host must be a valid IP or hostname')
            host = manual_host
            source = 'request'

        if not host:
            try:
                client = get_shared_gateway_client(tenant_code=device.tenant.code if device.tenant else None)
                payload = client.device_list_all(max_result=100, key=device.serial_number)
                for item in extract_devices(payload):
                    ehome = item.get('EhomeParams', {}) if isinstance(item.get('EhomeParams'), dict) else {}
                    same_index = str(item.get('devIndex') or '') == str(device.dev_index)
                    same_sn = str(ehome.get('EhomeID') or '') == str(device.serial_number)
                    if same_index or same_sn:
                        host, port = self._extract_host_and_port(item)
                        if host:
                            source = 'gateway'
                            break
            except Exception:
                host, port = '', None

        fallback_ip = (device.ip_address or '').strip()
        if not host and fallback_ip and fallback_ip != self._DEFAULT_GATEWAY_PLACEHOLDER_IP:
            host = fallback_ip

        if not host:
            return '', source

        scheme = str(request.query_params.get('scheme', 'http')).strip().lower()
        if scheme not in {'http', 'https'}:
            raise ValueError('scheme must be http or https')

        explicit_port = request.query_params.get('port')
        if explicit_port not in (None, ''):
            try:
                port = int(explicit_port)
            except (TypeError, ValueError):
                raise ValueError('port must be an integer') from None
            if not (1 <= port <= 65535):
                raise ValueError('port must be between 1 and 65535')

        path = str(request.query_params.get('path', '/')).strip() or '/'
        if not path.startswith('/'):
            path = f'/{path}'

        include_credentials = str(request.query_params.get('include_credentials', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
        credentials = ''
        if include_credentials and device.device_username:
            username = quote(device.device_username, safe='')
            password = quote(device.device_password or '', safe='')
            credentials = f'{username}:{password}@' if password else f'{username}@'

        netloc = f'{credentials}{host}'
        if port:
            netloc = f'{netloc}:{port}'

        return f'{scheme}://{netloc}{path}', source


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
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Device.objects.all().order_by('-id')
        owner_only = str(self.request.query_params.get('owner_only', '')).lower() in {'1', 'true', 'yes'}

        if owner_only and self.request.user.is_authenticated:
            return queryset.filter(owner=self.request.user)

        return queryset

    def _can_manage_device(self, user, device: Device) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or user.is_staff:
            return True
        return device.owner_id == user.id

    def _delete_device_from_gateway(self, device: Device):
        if not device.dev_index:
            return
        tenant_code = device.tenant.code if device.tenant else None
        gateway_client = get_shared_gateway_client(tenant_code=tenant_code)
        gateway_client.delete_device(dev_index=device.dev_index)

    def _push_employee_to_device(
        self,
        *,
        gateway_client,
        device: Device,
        employee: Employee,
        include_cards: bool = True,
    ) -> dict:
        if not device.dev_index:
            return {
                "status": "error",
                "employee_id": employee.id,
                "employee_no": employee.employee_no,
                "detail": "Le lecteur n'a pas de dev_index.",
            }

        user_payload = build_user_info_payload(employee)
        pushed_cards = 0
        card_errors = []
        try:
            user_response = gateway_client.add_access_user(dev_index=device.dev_index, payload=user_payload)
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
            # The person already exists on the reader; continue to allow card updates.
            if "employeeNoAlreadyExist" in detail:
                user_response = {
                    "statusCode": 1,
                    "statusString": "OK",
                    "subStatusCode": "employeeNoAlreadyExist",
                }
            else:
                return {
                    "status": "error",
                    "employee_id": employee.id,
                    "employee_no": employee.employee_no,
                    "detail": detail,
                }

        if include_cards:
            for payload in build_card_info_payloads(employee):
                try:
                    gateway_client.add_access_card(dev_index=device.dev_index, payload=payload)
                    pushed_cards += 1
                except Exception as exc:  # noqa: BLE001
                    card_errors.append(str(exc))

        status_string = str(user_response.get("statusString", "OK")).upper() if isinstance(user_response, dict) else "OK"
        sub_status = str(user_response.get("subStatusCode", "")).strip() if isinstance(user_response, dict) else ""
        user_ok = status_string in {"OK", "SUCCESS"} or sub_status in {"employeeNoAlreadyExist", ""}
        if not user_ok:
            return {
                "status": "error",
                "employee_id": employee.id,
                "employee_no": employee.employee_no,
                "detail": f"Gateway user push refuse: {user_response}",
            }

        if card_errors:
            return {
                "status": "partial",
                "employee_id": employee.id,
                "employee_no": employee.employee_no,
                "detail": "Personne ajoutee, mais au moins une carte a echoue.",
                "cards_pushed": pushed_cards,
                "card_errors": card_errors,
            }

        return {
            "status": "ok",
            "employee_id": employee.id,
            "employee_no": employee.employee_no,
            "cards_pushed": pushed_cards,
            "detail": "Personne ajoutee au lecteur.",
        }

    def destroy(self, request, *args, **kwargs):
        device = self.get_object()
        if not self._can_manage_device(request.user, device):
            return Response(
                {'detail': "Vous n'avez pas la permission de supprimer ce device."},
                status=status.HTTP_403_FORBIDDEN,
            )

        delete_on_gateway = str(request.query_params.get('gateway', '1')).strip().lower() in {'1', 'true', 'yes', 'on'}
        if delete_on_gateway:
            try:
                self._delete_device_from_gateway(device)
            except Exception as exc:  # noqa: BLE001
                return Response(
                    {'detail': f"Suppression gateway échouée: {exc}"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        self.perform_destroy(device)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def update(self, request, *args, **kwargs):
        device = self.get_object()
        if not self._can_manage_device(request.user, device):
            return Response(
                {'detail': "Vous n'avez pas la permission de modifier ce device."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        device = self.get_object()
        if not self._can_manage_device(request.user, device):
            return Response(
                {'detail': "Vous n'avez pas la permission de modifier ce device."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='delete')
    def delete(self, request, pk=None):
        return self.destroy(request, pk=pk)

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

    @action(detail=True, methods=['get'], url_path='config-page')
    def config_page(self, request, pk=None):
        device = self.get_object()
        try:
            configuration_url, source = self._build_device_config_url(request, device)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if not configuration_url:
            return Response(
                {'detail': "Impossible de construire l'URL de configuration pour ce device."},
                status=status.HTTP_404_NOT_FOUND,
            )

        wants_redirect = str(request.query_params.get('redirect', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
        if wants_redirect:
            return HttpResponseRedirect(configuration_url)

        return Response(
            {
                'device_id': device.id,
                'dev_index': device.dev_index,
                'serial_number': device.serial_number,
                'configuration_url': configuration_url,
                'source': source,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="add-persons")
    def add_persons(self, request, pk=None):
        device = self.get_object()
        if not device.tenant_id:
            return Response({"detail": "Lecteur sans tenant."}, status=status.HTTP_400_BAD_REQUEST)
        if not str(device.dev_index or "").strip():
            return Response({"detail": "Le lecteur n'a pas de dev_index."}, status=status.HTTP_400_BAD_REQUEST)

        employee_ids = request.data.get("employee_ids")
        if not isinstance(employee_ids, list) or not employee_ids:
            return Response(
                {"detail": "Le champ employee_ids est obligatoire et doit etre une liste non vide."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        include_cards = str(request.data.get("include_cards", True)).strip().lower() in {"1", "true", "yes", "on"}
        stop_on_error = str(request.data.get("stop_on_error", False)).strip().lower() in {"1", "true", "yes", "on"}

        employees = list(
            Employee.objects.filter(tenant_id=device.tenant_id, id__in=employee_ids)
            .prefetch_related("attributes", "cards")
            .order_by("id")
        )
        found_ids = {employee.id for employee in employees}
        missing_ids = [employee_id for employee_id in employee_ids if employee_id not in found_ids]
        if missing_ids:
            return Response(
                {"detail": f"Employés introuvables pour ce tenant: {missing_ids}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        gateway_client = get_shared_gateway_client(tenant_code=device.tenant.code if device.tenant else None)
        results = []
        success_count = 0
        partial_count = 0
        error_count = 0

        for employee in employees:
            result = self._push_employee_to_device(
                gateway_client=gateway_client,
                device=device,
                employee=employee,
                include_cards=include_cards,
            )
            results.append(result)
            if result["status"] == "ok":
                success_count += 1
            elif result["status"] == "partial":
                partial_count += 1
            else:
                error_count += 1
                if stop_on_error:
                    break

        response_status = status.HTTP_200_OK if error_count == 0 else status.HTTP_207_MULTI_STATUS
        return Response(
            {
                "status": "ok" if error_count == 0 else "partial",
                "device_id": device.id,
                "dev_index": device.dev_index,
                "total": len(results),
                "success_count": success_count,
                "partial_count": partial_count,
                "error_count": error_count,
                "results": results,
            },
            status=response_status,
        )


class DeviceOnboardingJobViewSet(viewsets.GenericViewSet):
    queryset = DeviceOnboardingJob.objects.none()
    serializer_class = DeviceOnboardingJobSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = DeviceOnboardingJob.objects.select_related("tenant", "organization", "requested_by", "device").order_by("-id")
        user = self.request.user
        if user.is_superuser or user.is_staff:
            return qs
        tenant_ids = TenantMembership.objects.filter(user=user).values_list("tenant_id", flat=True)
        return qs.filter(tenant_id__in=tenant_ids)

    def list(self, request):
        queryset = self.get_queryset()
        tenant_code = str(request.query_params.get("tenant_code") or "").strip()
        if tenant_code:
            queryset = queryset.filter(tenant__code__iexact=tenant_code)
        serializer = self.get_serializer(queryset[:200], many=True)
        return Response({"count": len(serializer.data), "results": serializer.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, pk=None):
        job = self.get_queryset().filter(id=pk).first()
        if job is None:
            return Response({"detail": "Onboarding job not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(job)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request):
        serializer = DeviceOnboardingJobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        tenant = Tenant.objects.filter(code__iexact=validated["tenant_code"]).first()
        if tenant is None:
            return Response({"detail": "Tenant not found."}, status=status.HTTP_400_BAD_REQUEST)

        organization = Organization.objects.filter(id=validated["organization_id"], tenant=tenant).first()
        if organization is None:
            return Response({"detail": "Organization not found for this tenant."}, status=status.HTTP_400_BAD_REQUEST)

        job = create_job(
            user=request.user,
            tenant=tenant,
            organization=organization,
            sn=validated["sn"],
            dev_name=validated["dev_name"],
            dev_type=validated["dev_type"],
            device_username=validated.get("device_username", ""),
            device_password=validated.get("device_password", ""),
        )

        process_now = str(request.query_params.get("process_now", "")).strip().lower() in {"1", "true", "yes", "on"}
        if job.status == DeviceOnboardingJob.STATUS_PENDING:
            if process_now:
                job = process_job(job_id=job.id, ehome_key=validated["ehome_key"])
            else:
                schedule_job(job_id=job.id, ehome_key=validated["ehome_key"])

        output = self.get_serializer(job)
        return Response(output.data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        job = self.get_queryset().filter(id=pk).first()
        if job is None:
            return Response({"detail": "Onboarding job not found."}, status=status.HTTP_404_NOT_FOUND)

        if not has_tenant_role(request.user, job.tenant, TenantRole.ORG_ADMIN):
            if not has_organization_role(request.user, job.organization, allowed_org_roles=("org_admin",)):
                return Response({"detail": "Insufficient role to approve this job."}, status=status.HTTP_403_FORBIDDEN)

        ehome_key = str(request.data.get("ehome_key") or "").strip()
        if not ehome_key:
            return Response({"detail": "ehome_key is required to process the job."}, status=status.HTTP_400_BAD_REQUEST)

        if job.status == DeviceOnboardingJob.STATUS_MANUAL_REVIEW:
            job.status = DeviceOnboardingJob.STATUS_PENDING
            job.review_reason = DeviceOnboardingJob.REVIEW_NONE
            job.save(update_fields=["status", "review_reason", "updated_at"])

        process_now = str(request.query_params.get("process_now", "1")).strip().lower() in {"1", "true", "yes", "on"}
        if process_now:
            job = process_job(job_id=job.id, ehome_key=ehome_key)
        else:
            schedule_job(job_id=job.id, ehome_key=ehome_key)
            job.refresh_from_db()

        output = self.get_serializer(job)
        return Response(output.data, status=status.HTTP_200_OK)
