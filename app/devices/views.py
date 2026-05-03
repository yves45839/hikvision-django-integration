import base64
import binascii
import time as pytime
from datetime import datetime
from datetime import timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from employees.models import Employee, EmployeeFace, EmployeeFingerprint, Organization
from employees.services import build_card_info_payloads, build_fingerprint_cfg_payloads, build_user_info_payload
from hik_gateway.services.device_payload import extract_devices
from hik_gateway.services.gateway_connection import get_shared_gateway_client
from tenants.models import Tenant, TenantRole
from tenants.services import has_organization_role, has_tenant_role, scope_queryset_to_user_tenants

from .models import Device, DeviceOnboardingJob
from .serializers import (
    DeviceOnboardSerializer,
    DeviceOnboardingJobCreateSerializer,
    DeviceOnboardingJobSerializer,
    DeviceSerializer,
)
from .services.onboarding import create_job, process_job, schedule_job


class DeviceViewSet(viewsets.ModelViewSet):
    @staticmethod
    def _to_bool(value, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off"}:
            return False
        return default

    @staticmethod
    def _decode_face_data(face_data_raw: str) -> tuple[bytes, str]:
        text = str(face_data_raw or "").strip()
        if not text:
            raise ValueError("face_data est vide.")

        content_type = "image/jpeg"
        if text.lower().startswith("data:"):
            header, separator, payload = text.partition(",")
            if not separator:
                raise ValueError("face_data (data URI) est invalide.")
            text = payload.strip()
            mime_part = header[5:].split(";", 1)[0].strip()
            if mime_part:
                content_type = mime_part

        normalized = "".join(text.split())
        if not normalized:
            raise ValueError("face_data est vide.")
        try:
            image_bytes = base64.b64decode(normalized, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("face_data doit etre une image base64 valide.") from exc

        if not image_bytes:
            raise ValueError("face_data ne contient pas de donnees image.")
        return image_bytes, content_type

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

    @staticmethod
    def _build_manual_local_time(value: str | None, gmt_offset: str | None) -> str:
        raw_dt = str(value or "").strip()
        offset = str(gmt_offset or "").strip() or "+00:00"
        if len(offset) != 6 or offset[0] not in {"+", "-"} or offset[3] != ":":
            raise ValueError("gmt_offset doit etre au format +HH:MM ou -HH:MM.")

        try:
            int(offset[1:3])
            int(offset[4:6])
        except ValueError as exc:
            raise ValueError("gmt_offset doit etre au format +HH:MM ou -HH:MM.") from exc

        if raw_dt:
            normalized_dt = raw_dt.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized_dt)
            except ValueError as exc:
                raise ValueError("local_time doit etre un datetime ISO-8601 valide.") from exc
        else:
            parsed = datetime.now(dt_timezone.utc)

        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        return f"{parsed.strftime('%Y-%m-%dT%H:%M:%S')}{offset}"

    queryset = Device.objects.none()
    serializer_class = DeviceSerializer
    permission_classes = [IsAuthenticated]

    def _require_tenant_scope(self, tenant: Tenant | None) -> None:
        if tenant is None:
            raise PermissionDenied("Tenant is required for this action.")
        if has_tenant_role(self.request.user, tenant, TenantRole.VIEWER):
            return
        raise PermissionDenied("Insufficient tenant scope for this action.")

    def get_queryset(self):
        queryset = Device.objects.all().order_by('-id')
        queryset = scope_queryset_to_user_tenants(queryset, self.request.user, tenant_field="tenant_id")
        owner_only = str(self.request.query_params.get('owner_only', '')).lower() in {'1', 'true', 'yes'}

        if owner_only and self.request.user.is_authenticated:
            return queryset.filter(owner=self.request.user)

        return queryset

    def perform_create(self, serializer):
        tenant = serializer.validated_data.get("tenant")
        self._require_tenant_scope(tenant)
        serializer.save(owner=self.request.user)

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

    def _reboot_device_on_gateway(self, device: Device):
        if not device.dev_index:
            return
        tenant_code = device.tenant.code if device.tenant else None
        gateway_client = get_shared_gateway_client(tenant_code=tenant_code)
        return gateway_client.reboot_device(dev_index=device.dev_index)

    def _set_device_time_on_gateway(
        self,
        *,
        device: Device,
        time_payload: dict,
        time_zone: str | None = None,
    ) -> tuple[dict, dict | None]:
        if not device.dev_index:
            return {}, None
        tenant_code = device.tenant.code if device.tenant else None
        gateway_client = get_shared_gateway_client(tenant_code=tenant_code)
        time_response = gateway_client.set_device_time_sync(dev_index=device.dev_index, payload=time_payload)
        timezone_response = None
        if str(time_zone or "").strip():
            timezone_response = gateway_client.set_device_time_zone(
                dev_index=device.dev_index,
                time_zone=str(time_zone).strip(),
            )
        return time_response, timezone_response

    def _push_employee_to_device(
        self,
        *,
        gateway_client,
        device: Device,
        employee: Employee,
        include_cards: bool = True,
        include_fingerprints: bool = True,
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
        pushed_fingerprints = 0
        card_errors = []
        fingerprint_errors = []
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

        if include_fingerprints:
            for payload in build_fingerprint_cfg_payloads(employee):
                try:
                    gateway_client.add_access_fingerprint(dev_index=device.dev_index, payload=payload)
                    pushed_fingerprints += 1
                except Exception as exc:  # noqa: BLE001
                    detail = str(exc)
                    normalized_detail = detail.lower()
                    if "fingerprintidalreadyexist" in normalized_detail or "fingerprintalreadyexist" in normalized_detail:
                        continue
                    fingerprint_errors.append(detail)

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

        if card_errors or fingerprint_errors:
            return {
                "status": "partial",
                "employee_id": employee.id,
                "employee_no": employee.employee_no,
                "detail": "Personne ajoutee, mais au moins un credential a echoue.",
                "cards_pushed": pushed_cards,
                "fingerprints_pushed": pushed_fingerprints,
                "card_errors": card_errors,
                "fingerprint_errors": fingerprint_errors,
            }

        return {
            "status": "ok",
            "employee_id": employee.id,
            "employee_no": employee.employee_no,
            "cards_pushed": pushed_cards,
            "fingerprints_pushed": pushed_fingerprints,
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

    @action(detail=True, methods=['post'], url_path='reboot')
    def reboot(self, request, pk=None):
        device = self.get_object()
        if not self._can_manage_device(request.user, device):
            return Response(
                {'detail': "Vous n'avez pas la permission de redemarrer ce device."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not str(device.dev_index or '').strip():
            return Response(
                {'detail': "Le device n'a pas de dev_index."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            gateway_response = self._reboot_device_on_gateway(device)
        except Exception as exc:  # noqa: BLE001
            return Response(
                {'detail': f"Echec redemarrage gateway: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {
                'status': 'accepted',
                'detail': 'Commande de redemarrage envoyee au device.',
                'dev_index': device.dev_index,
                'gateway_response': gateway_response if isinstance(gateway_response, dict) else {},
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=['post'], url_path='set-time')
    def set_time(self, request, pk=None):
        device = self.get_object()
        if not self._can_manage_device(request.user, device):
            return Response(
                {'detail': "Vous n'avez pas la permission de mettre a l'heure ce device."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not str(device.dev_index or '').strip():
            return Response(
                {'detail': "Le device n'a pas de dev_index."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        mode = str(request.data.get('mode') or 'manual').strip()
        if mode.lower() == 'ntp':
            normalized_mode = 'NTP'
            time_payload = {'Time': {'timeMode': normalized_mode}}
        elif mode.lower() == 'manual':
            try:
                local_time = self._build_manual_local_time(
                    request.data.get('local_time'),
                    request.data.get('gmt_offset'),
                )
            except ValueError as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            normalized_mode = 'manual'
            time_payload = {'Time': {'timeMode': normalized_mode, 'localTime': local_time}}
        else:
            return Response(
                {'detail': "mode doit etre 'manual' ou 'NTP'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        time_zone = request.data.get('time_zone')
        if time_zone is not None and not str(time_zone).strip():
            return Response(
                {'detail': "time_zone ne peut pas etre vide quand il est fourni."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            gateway_response, timezone_response = self._set_device_time_on_gateway(
                device=device,
                time_payload=time_payload,
                time_zone=str(time_zone).strip() if time_zone is not None else None,
            )
        except Exception as exc:  # noqa: BLE001
            return Response(
                {'detail': f"Echec synchronisation heure device: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        response_payload = {
            'status': 'accepted',
            'detail': 'Commande de synchronisation horaire envoyee au device.',
            'dev_index': device.dev_index,
            'applied': {
                'mode': normalized_mode,
                'time_payload': time_payload,
                'time_zone': str(time_zone).strip() if time_zone is not None else None,
            },
            'gateway_response': gateway_response if isinstance(gateway_response, dict) else {},
        }
        if timezone_response is not None:
            response_payload['gateway_time_zone_response'] = (
                timezone_response if isinstance(timezone_response, dict) else {}
            )
        return Response(response_payload, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=['post'], url_path='onboard')
    def onboard(self, request):
        serializer = DeviceOnboardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        tenant = Tenant.objects.filter(code__iexact=validated['tenant_code']).first()
        if tenant is None:
            return Response({'detail': 'Tenant introuvable.'}, status=status.HTTP_400_BAD_REQUEST)
        self._require_tenant_scope(tenant)

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

        include_cards = self._to_bool(request.data.get("include_cards", True), default=True)
        include_fingerprints = self._to_bool(request.data.get("include_fingerprints", True), default=True)
        stop_on_error = self._to_bool(request.data.get("stop_on_error", False), default=False)

        employees = list(
            Employee.objects.filter(tenant_id=device.tenant_id, id__in=employee_ids)
            .prefetch_related("attributes", "cards", "fingerprints")
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
                include_fingerprints=include_fingerprints,
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

    @action(detail=True, methods=["post"], url_path="enroll-fingerprint")
    def enroll_fingerprint(self, request, pk=None):
        device = self.get_object()
        if not device.tenant_id:
            return Response({"detail": "Lecteur sans tenant."}, status=status.HTTP_400_BAD_REQUEST)
        if not str(device.dev_index or "").strip():
            return Response({"detail": "Le lecteur n'a pas de dev_index."}, status=status.HTTP_400_BAD_REQUEST)

        employee_id = request.data.get("employee_id")
        if not employee_id:
            return Response({"detail": "employee_id est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

        finger_index_raw = request.data.get("finger_index")
        try:
            finger_index = int(finger_index_raw)
        except (TypeError, ValueError):
            return Response({"detail": "finger_index doit etre un entier entre 1 et 10."}, status=status.HTTP_400_BAD_REQUEST)
        if not 1 <= finger_index <= 10:
            return Response({"detail": "finger_index doit etre entre 1 et 10."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            quality_threshold = int(request.data.get("quality_threshold", 0) or 0)
        except (TypeError, ValueError):
            return Response({"detail": "quality_threshold doit etre un entier."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            capture_retries = int(request.data.get("capture_retries", 3) or 3)
        except (TypeError, ValueError):
            return Response({"detail": "capture_retries doit etre un entier."}, status=status.HTTP_400_BAD_REQUEST)
        capture_retries = max(1, min(capture_retries, 8))

        include_cards = self._to_bool(request.data.get("include_cards", False), default=False)
        push_to_all_readers = self._to_bool(request.data.get("push_to_all_readers", True), default=True)

        employee = (
            Employee.objects.filter(tenant_id=device.tenant_id, id=employee_id)
            .select_related("tenant", "department")
            .prefetch_related("attributes", "cards", "fingerprints", "devices", "department__devices", "access_groups__readers")
            .first()
        )
        if employee is None:
            return Response({"detail": "Employe introuvable pour ce tenant."}, status=status.HTTP_404_NOT_FOUND)

        gateway_client = get_shared_gateway_client(tenant_code=device.tenant.code if device.tenant else None)
        capture_response = {}
        capture_error = None
        capture_attempts = 0
        finger_data = ""
        capture = {}
        for attempt in range(1, capture_retries + 1):
            capture_attempts = attempt
            try:
                capture_response = gateway_client.capture_fingerprint(
                    dev_index=device.dev_index,
                    finger_no=finger_index,
                )
            except Exception as exc:  # noqa: BLE001
                capture_error = str(exc)
            else:
                capture = capture_response.get("CaptureFingerPrint", {}) if isinstance(capture_response, dict) else {}
                finger_data = str(capture.get("fingerData") or "").strip() if isinstance(capture, dict) else ""
                if finger_data:
                    capture_error = None
                    break
                capture_error = "Le lecteur n'a pas retourne de donnees d'empreinte."

            if attempt < capture_retries:
                pytime.sleep(1.0)

        if not finger_data:
            detail = capture_error or "Echec de collecte empreinte."
            return Response(
                {
                    "detail": detail,
                    "capture_attempts": capture_attempts,
                    "capture_response": capture_response,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        finger_quality = None
        if isinstance(capture, dict):
            try:
                finger_quality = int(capture.get("fingerPrintQuality"))
            except (TypeError, ValueError):
                finger_quality = None

        if quality_threshold > 0 and finger_quality is not None and finger_quality < quality_threshold:
            return Response(
                {
                    "detail": "Qualite empreinte insuffisante.",
                    "finger_quality": finger_quality,
                    "quality_threshold": quality_threshold,
                },
                status=status.HTTP_409_CONFLICT,
            )

        EmployeeFingerprint.objects.update_or_create(
            employee=employee,
            finger_index=finger_index,
            defaults={"template": finger_data},
        )

        # Reload prefetched credentials for immediate push.
        employee = (
            Employee.objects.filter(id=employee.id)
            .select_related("tenant", "department")
            .prefetch_related("attributes", "cards", "fingerprints", "devices", "department__devices", "access_groups__readers")
            .first()
        )
        if employee is None:
            return Response({"detail": "Employe introuvable apres sauvegarde."}, status=status.HTTP_404_NOT_FOUND)

        if push_to_all_readers:
            target_readers = list(employee.get_effective_devices(include_department_ancestors=True))
            if all(reader.id != device.id for reader in target_readers):
                target_readers.append(device)
        else:
            target_readers = [device]

        deduped_readers = []
        seen_reader_ids = set()
        for reader in target_readers:
            if reader.id in seen_reader_ids:
                continue
            seen_reader_ids.add(reader.id)
            deduped_readers.append(reader)

        results = []
        success_count = 0
        partial_count = 0
        error_count = 0

        for reader in deduped_readers:
            result = self._push_employee_to_device(
                gateway_client=gateway_client,
                device=reader,
                employee=employee,
                include_cards=include_cards,
                include_fingerprints=True,
            )
            results.append(
                {
                    "reader_id": reader.id,
                    "dev_index": reader.dev_index,
                    **result,
                }
            )
            if result["status"] == "ok":
                success_count += 1
            elif result["status"] == "partial":
                partial_count += 1
            else:
                error_count += 1

        response_status = status.HTTP_200_OK if error_count == 0 else status.HTTP_207_MULTI_STATUS
        return Response(
            {
                "status": "ok" if error_count == 0 else "partial",
                "employee_id": employee.id,
                "employee_no": employee.employee_no,
                "finger_index": finger_index,
                "finger_quality": finger_quality,
                "finger_template": finger_data,
                "capture_attempts": capture_attempts,
                "captured_on_reader": {
                    "device_id": device.id,
                    "dev_index": device.dev_index,
                },
                "target_readers_count": len(results),
                "success_count": success_count,
                "partial_count": partial_count,
                "error_count": error_count,
                "results": results,
            },
            status=response_status,
        )

    @action(detail=True, methods=["post"], url_path="enroll-face")
    def enroll_face(self, request, pk=None):
        device = self.get_object()
        if not device.tenant_id:
            return Response({"detail": "Lecteur sans tenant."}, status=status.HTTP_400_BAD_REQUEST)
        if not str(device.dev_index or "").strip():
            return Response({"detail": "Le lecteur n'a pas de dev_index."}, status=status.HTTP_400_BAD_REQUEST)

        employee_id = request.data.get("employee_id")
        if not employee_id:
            return Response({"detail": "employee_id est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

        include_cards = self._to_bool(request.data.get("include_cards", False), default=False)
        include_fingerprints = self._to_bool(request.data.get("include_fingerprints", False), default=False)
        push_to_all_readers = self._to_bool(request.data.get("push_to_all_readers", True), default=True)

        face_lib_type = str(request.data.get("face_lib_type") or "blackFD").strip() or "blackFD"
        if face_lib_type not in {"infraredFD", "blackFD", "staticFD"}:
            return Response(
                {"detail": "face_lib_type invalide. Valeurs autorisees: infraredFD, blackFD, staticFD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        employee = (
            Employee.objects.filter(tenant_id=device.tenant_id, id=employee_id)
            .select_related("tenant", "department", "face")
            .prefetch_related("attributes", "cards", "fingerprints", "devices", "department__devices", "access_groups__readers")
            .first()
        )
        if employee is None:
            return Response({"detail": "Employe introuvable pour ce tenant."}, status=status.HTTP_404_NOT_FOUND)

        requested_face_data = request.data.get("face_data")
        if requested_face_data is not None and str(requested_face_data).strip():
            EmployeeFace.objects.update_or_create(
                employee=employee,
                defaults={"face_data": str(requested_face_data).strip()},
            )

        employee = (
            Employee.objects.filter(id=employee.id)
            .select_related("tenant", "department", "face")
            .prefetch_related("attributes", "cards", "fingerprints", "devices", "department__devices", "access_groups__readers")
            .first()
        )
        if employee is None:
            return Response({"detail": "Employe introuvable apres sauvegarde."}, status=status.HTTP_404_NOT_FOUND)

        try:
            face_data = str(employee.face.face_data or "").strip()
        except EmployeeFace.DoesNotExist:
            face_data = ""
        if not face_data:
            return Response(
                {"detail": "Aucune photo visage disponible. Importez une photo ou envoyez face_data."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            face_image, face_content_type = self._decode_face_data(face_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        user_payload = build_user_info_payload(employee)
        user_info = user_payload.get("UserInfo", {}) if isinstance(user_payload, dict) else {}
        employee_no = str(user_info.get("employeeNo") or "").strip()
        if not employee_no:
            return Response(
                {"detail": "Impossible de resoudre employeeNo pour l'enrolement visage."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if push_to_all_readers:
            target_readers = list(employee.get_effective_devices(include_department_ancestors=True))
            if all(reader.id != device.id for reader in target_readers):
                target_readers.append(device)
        else:
            target_readers = [device]

        deduped_readers = []
        seen_reader_ids = set()
        for reader in target_readers:
            if reader.id in seen_reader_ids:
                continue
            seen_reader_ids.add(reader.id)
            deduped_readers.append(reader)

        gateway_client = get_shared_gateway_client(tenant_code=device.tenant.code if device.tenant else None)

        results = []
        success_count = 0
        partial_count = 0
        error_count = 0

        for reader in deduped_readers:
            person_result = self._push_employee_to_device(
                gateway_client=gateway_client,
                device=reader,
                employee=employee,
                include_cards=include_cards,
                include_fingerprints=include_fingerprints,
            )

            face_response = None
            face_error = None
            if person_result.get("status") == "error":
                face_error = person_result.get("detail") or "Impossible de preparer la personne sur le lecteur."
                result_status = "error"
            else:
                try:
                    face_response = gateway_client.add_access_face(
                        dev_index=reader.dev_index,
                        employee_no=employee_no,
                        face_image=face_image,
                        face_lib_type=face_lib_type,
                        content_type=face_content_type,
                    )
                except Exception as exc:  # noqa: BLE001
                    face_error = str(exc)
                    result_status = "error"
                else:
                    result_status = "partial" if person_result.get("status") == "partial" else "ok"

            if result_status == "ok":
                success_count += 1
            elif result_status == "partial":
                partial_count += 1
            else:
                error_count += 1

            result_payload = {
                "reader_id": reader.id,
                "dev_index": reader.dev_index,
                "status": result_status,
                "person_push": person_result,
            }
            if face_response is not None:
                result_payload["face_response"] = face_response
            if face_error:
                result_payload["detail"] = face_error
            results.append(result_payload)

        response_status = status.HTTP_200_OK if error_count == 0 else status.HTTP_207_MULTI_STATUS
        return Response(
            {
                "status": "ok" if error_count == 0 else "partial",
                "employee_id": employee.id,
                "employee_no": employee.employee_no,
                "face_lib_type": face_lib_type,
                "captured_on_reader": {
                    "device_id": device.id,
                    "dev_index": device.dev_index,
                },
                "target_readers_count": len(results),
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
        return scope_queryset_to_user_tenants(qs, self.request.user, tenant_field="tenant_id")

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
        if not has_tenant_role(request.user, tenant, TenantRole.VIEWER):
            return Response({"detail": "Insufficient tenant scope for this tenant."}, status=status.HTTP_403_FORBIDDEN)

        organization = Organization.objects.filter(id=validated["organization_id"], tenant=tenant).first()
        if organization is None:
            return Response({"detail": "Organization not found for this tenant."}, status=status.HTTP_400_BAD_REQUEST)
        if not has_organization_role(
            request.user,
            organization,
            allowed_org_roles=("org_admin", "operator", "viewer"),
        ) and not has_tenant_role(request.user, tenant, TenantRole.ORG_ADMIN):
            return Response(
                {"detail": "Insufficient organization scope for this tenant."},
                status=status.HTTP_403_FORBIDDEN,
            )

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
