from __future__ import annotations

import threading

from django.conf import settings
from django.db import transaction, close_old_connections
from django.utils import timezone

from devices.models import Device, DeviceOnboardingJob, DeviceOrganizationBinding
from employees.models import Organization
from hik_gateway.services.device_payload import extract_devices
from hik_gateway.services.gateway_connection import get_shared_gateway_client
from tenants.services import has_organization_role


def evaluate_auto_acceptance(*, user, tenant, organization) -> str:
    if not tenant.is_active:
        return DeviceOnboardingJob.REVIEW_TENANT_INACTIVE
    if not tenant.is_domain_verified:
        return DeviceOnboardingJob.REVIEW_DOMAIN_NOT_VERIFIED
    if not has_organization_role(user, organization):
        return DeviceOnboardingJob.REVIEW_PERMISSION_DENIED
    if tenant.device_quota and Device.objects.filter(tenant=tenant).count() >= tenant.device_quota:
        return DeviceOnboardingJob.REVIEW_QUOTA_EXCEEDED
    return DeviceOnboardingJob.REVIEW_NONE


def build_http_host_payload() -> dict | None:
    webhook_url = (getattr(settings, "HIK_WEBHOOK_URL", "") or "").strip()
    webhook_ip = (getattr(settings, "HIK_WEBHOOK_IP", "") or "").strip()
    webhook_port = int(getattr(settings, "HIK_WEBHOOK_PORT", 443) or 443)
    if not webhook_url or not webhook_ip:
        return None
    return {
        "HttpHostNotificationList": [
            {
                "HttpHostNotification": {
                    "id": "1",
                    "url": webhook_url,
                    "protocolType": "HTTP",
                    "addressingFormatType": "ipaddress",
                    "ipAddress": webhook_ip,
                    "portNo": webhook_port,
                    "enable": True,
                    "SubscribeEvent": {
                        "heartbeat": 30,
                        "eventMode": "all",
                    },
                }
            }
        ]
    }


def _create_or_update_binding(device: Device, organization: Organization, user):
    binding, _ = DeviceOrganizationBinding.objects.update_or_create(
        device=device,
        organization=organization,
        defaults={
            "assigned_by": user if user and user.is_authenticated else None,
        },
    )
    return binding


def create_job(
    *,
    user,
    tenant,
    organization,
    sn: str,
    dev_name: str,
    dev_type: str,
    device_username: str = "",
    device_password: str = "",
) -> DeviceOnboardingJob:
    review_reason = evaluate_auto_acceptance(user=user, tenant=tenant, organization=organization)
    initial_status = (
        DeviceOnboardingJob.STATUS_MANUAL_REVIEW
        if review_reason != DeviceOnboardingJob.REVIEW_NONE
        else DeviceOnboardingJob.STATUS_PENDING
    )
    return DeviceOnboardingJob.objects.create(
        tenant=tenant,
        organization=organization,
        requested_by=user if user and user.is_authenticated else None,
        status=initial_status,
        review_reason=review_reason,
        sn=sn,
        dev_name=dev_name,
        dev_type=dev_type,
        device_username=device_username or "",
        device_password=device_password or "",
        request_payload={
            "sn": sn,
            "dev_name": dev_name,
            "dev_type": dev_type,
            "organization_id": organization.id,
        },
    )


def process_job(*, job_id: int, ehome_key: str) -> DeviceOnboardingJob:
    with transaction.atomic():
        job = (
            DeviceOnboardingJob.objects.select_for_update()
            .select_related("tenant", "organization", "requested_by")
            .get(id=job_id)
        )
        if job.status != DeviceOnboardingJob.STATUS_PENDING:
            return job
        job.status = DeviceOnboardingJob.STATUS_PROCESSING
        job.started_at = timezone.now()
        job.error_message = ""
        job.save(update_fields=["status", "started_at", "error_message", "updated_at"])

    try:
        tenant = job.tenant
        organization = job.organization

        existing_other_tenant = Device.objects.filter(serial_number=job.sn).exclude(tenant=tenant).first()
        if existing_other_tenant:
            job.status = DeviceOnboardingJob.STATUS_FAILED
            job.error_message = "Serial number already assigned to another tenant."
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "error_message", "completed_at", "updated_at"])
            return job

        existing_device = Device.objects.filter(serial_number=job.sn, tenant=tenant).first()
        if existing_device:
            _create_or_update_binding(existing_device, organization, job.requested_by)
            job.status = DeviceOnboardingJob.STATUS_COMPLETED
            job.device = existing_device
            job.completed_at = timezone.now()
            job.gateway_status = {"status": "already_exists", "devIndex": existing_device.dev_index}
            job.save(update_fields=["status", "device", "gateway_status", "completed_at", "updated_at"])
            return job

        gateway_client = get_shared_gateway_client(tenant_code=tenant.code)
        payload = {
            "DeviceInList": [
                {
                    "Device": {
                        "protocolType": "ehomeV5",
                        "EhomeParams": {
                            "EhomeID": job.sn,
                            "EhomeKey": ehome_key,
                        },
                        "devName": job.dev_name,
                        "devType": job.dev_type,
                    }
                }
            ]
        }
        add_response = gateway_client.add_device(payload=payload)
        device_out_list = add_response.get("DeviceOutList", {}) if isinstance(add_response, dict) else {}
        out_devices = device_out_list.get("Device", []) if isinstance(device_out_list, dict) else []
        if isinstance(out_devices, dict):
            out_devices = [out_devices]
        out_device = out_devices[0] if out_devices else {}

        add_status = str(out_device.get("status", "")).lower()
        sub_status_code = out_device.get("subStatusCode", "")
        if add_status not in {"", "ok", "success"} and sub_status_code != "deviceExist":
            job.status = DeviceOnboardingJob.STATUS_FAILED
            job.error_message = "Gateway rejected device onboarding."
            job.gateway_status = out_device
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "error_message", "gateway_status", "completed_at", "updated_at"])
            return job

        dev_index = out_device.get("devIndex") or ""
        if not dev_index:
            search_payload = gateway_client.device_list_all(
                max_result=100,
                protocol_types=["ehomeV5"],
                dev_type=job.dev_type,
                key=job.sn,
            )
            for item in extract_devices(search_payload):
                ehome = item.get("EhomeParams", {}) if isinstance(item.get("EhomeParams"), dict) else {}
                if str(ehome.get("EhomeID") or "").strip() == job.sn:
                    dev_index = str(item.get("devIndex") or "").strip()
                    if dev_index:
                        break

        if not dev_index:
            job.status = DeviceOnboardingJob.STATUS_FAILED
            job.error_message = "devIndex not found after gateway onboarding."
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "error_message", "completed_at", "updated_at"])
            return job

        webhook_payload = build_http_host_payload()
        if webhook_payload:
            try:
                gateway_client.set_http_host(dev_index=dev_index, payload=webhook_payload)
            except Exception as exc:  # noqa: BLE001
                job.gateway_status = {
                    "warning": f"webhook registration failed: {exc}",
                    "devIndex": dev_index,
                }

        with transaction.atomic():
            device = Device.objects.create(
                owner=job.requested_by,
                tenant=tenant,
                serial_number=job.sn,
                dev_index=dev_index,
                name=job.dev_name,
                protocol="ehomeV5",
                status="online",
                device_username=job.device_username,
                device_password=job.device_password,
            )
            _create_or_update_binding(device, organization, job.requested_by)

            job.device = device
            job.status = DeviceOnboardingJob.STATUS_COMPLETED
            job.gateway_status = out_device
            job.completed_at = timezone.now()
            job.save(update_fields=["device", "status", "gateway_status", "completed_at", "updated_at"])
        return job
    except Exception as exc:  # noqa: BLE001
        job = DeviceOnboardingJob.objects.get(id=job_id)
        job.status = DeviceOnboardingJob.STATUS_FAILED
        job.error_message = str(exc)
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "error_message", "completed_at", "updated_at"])
        return job


def schedule_job(*, job_id: int, ehome_key: str):
    def _runner():
        close_old_connections()
        try:
            process_job(job_id=job_id, ehome_key=ehome_key)
        finally:
            close_old_connections()

    thread = threading.Thread(target=_runner, name=f"device-onboarding-{job_id}", daemon=True)
    thread.start()
    return thread
