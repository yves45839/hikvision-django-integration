"""Services du pointage mobile — invitations employé."""
from __future__ import annotations

import secrets
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from employees.models import Employee
from presence.models import EmployeeInvitation, hash_invitation_secret
from tenants.emails import send_branded_email
from tenants.models import TenantMembership, TenantRole

User = get_user_model()


class InvitationError(Exception):
    """Erreur métier d'invitation, portant un code stable pour l'API."""

    def __init__(self, code: str, detail: str, http_status: int):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.http_status = http_status


@dataclass
class CreatedInvitation:
    invitation: EmployeeInvitation
    secret: str
    email_sent: bool


def create_mobile_invitation(*, employee: Employee, invited_by, email: str | None = None) -> CreatedInvitation:
    """Crée (et envoie) une invitation mobile pour un employé.

    Révoque toute invitation pending antérieure. Le secret n'est jamais
    persisté : seul son hash l'est.
    """
    target_email = (email or employee.email or "").strip().lower()
    if not target_email:
        raise InvitationError("NO_EMAIL", "L'employé n'a pas d'adresse email.", 400)
    if employee.user_id is not None:
        raise InvitationError("ALREADY_LINKED", "Cet employé a déjà un compte mobile.", 409)

    secret = secrets.token_urlsafe(32)

    with transaction.atomic():
        EmployeeInvitation.objects.filter(
            employee=employee, status=EmployeeInvitation.STATUS_PENDING
        ).update(status=EmployeeInvitation.STATUS_REVOKED)
        invitation = EmployeeInvitation.objects.create(
            tenant=employee.tenant,
            employee=employee,
            email=target_email,
            token_hash=hash_invitation_secret(secret),
            invited_by=invited_by,
        )

    frontend_base = getattr(settings, "FRONTEND_AUTH_BASE_URL", "http://localhost:3000").rstrip("/")
    email_sent = send_branded_email(
        to_email=target_email,
        template_name="mobile_invitation",
        context={
            "employee_name": employee.name,
            "tenant_name": employee.tenant.name,
            "deep_link": f"lrtime://accept-invitation?token={secret}",
            "web_fallback_url": f"{frontend_base}/mobile-invite?token={secret}",
            "invitation_token": secret,
            "expires_at": invitation.expires_at,
        },
        fail_silently=True,
    )
    return CreatedInvitation(invitation=invitation, secret=secret, email_sent=email_sent)


def get_invitation_by_secret(secret: str) -> EmployeeInvitation:
    token_hash = hash_invitation_secret(str(secret or "").strip())
    invitation = (
        EmployeeInvitation.objects.select_related("employee", "employee__tenant", "tenant")
        .filter(token_hash=token_hash)
        .first()
    )
    if invitation is None:
        raise InvitationError("INVALID_TOKEN", "Invitation introuvable.", 404)
    if invitation.status == EmployeeInvitation.STATUS_REVOKED:
        raise InvitationError("INVALID_TOKEN", "Invitation révoquée.", 404)
    if invitation.status == EmployeeInvitation.STATUS_ACCEPTED:
        raise InvitationError("ALREADY_LINKED", "Invitation déjà utilisée.", 409)
    if invitation.is_expired:
        raise InvitationError("EXPIRED", "Invitation expirée.", 410)
    return invitation


def _build_username(invitation: EmployeeInvitation) -> str:
    if not User.objects.filter(username__iexact=invitation.email).exists():
        return invitation.email
    return f"{invitation.tenant.code}_{invitation.employee.employee_no}".lower()


def accept_mobile_invitation(*, secret: str, password: str) -> tuple[EmployeeInvitation, "User"]:
    """Accepte une invitation : crée le compte, lie l'employé, membership employee."""
    invitation = get_invitation_by_secret(secret)
    employee = invitation.employee

    if employee.user_id is not None:
        raise InvitationError("ALREADY_LINKED", "Cet employé a déjà un compte mobile.", 409)
    if User.objects.filter(email__iexact=invitation.email).exists():
        raise InvitationError(
            "EMAIL_IN_USE", "Un compte existe déjà avec cette adresse email.", 409
        )
    try:
        validate_password(password)
    except DjangoValidationError as exc:
        raise InvitationError("WEAK_PASSWORD", " ".join(exc.messages), 400)

    with transaction.atomic():
        user = User.objects.create_user(
            username=_build_username(invitation),
            email=invitation.email,
            password=password,
            is_active=True,
        )
        employee.user = user
        employee.save(update_fields=["user", "updated_at"])
        # get_or_create : si un membership existe déjà (ex. rôle admin), on ne
        # rétrograde JAMAIS — on se contente de lier la fiche employé.
        TenantMembership.objects.get_or_create(
            user=user,
            tenant=invitation.tenant,
            defaults={"role": TenantRole.EMPLOYEE},
        )
        invitation.status = EmployeeInvitation.STATUS_ACCEPTED
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["status", "accepted_at", "updated_at"])

    return invitation, user


# ─── Pointage mobile ────────────────────────────────────────────────────────

MOBILE_DEV_INDEX = "MOBILE"
MOBILE_GATEWAY_BASE_URL = "https://mobile.invalid"


def get_mobile_device(tenant):
    """Appareil virtuel « Pointage mobile » du tenant (créé à la demande).

    kind=mobile_virtual : les services passerelle (synchro, health check,
    commandes) le sélectionnent par capacité et l'ignorent — aucun appel HTTP
    vers l'URL sentinelle.
    """
    from hik_gateway.models import Device as HikDevice, Gateway

    gateway, _ = Gateway.objects.get_or_create(
        tenant=tenant,
        kind=Gateway.KIND_MOBILE_VIRTUAL,
        defaults={"base_url": MOBILE_GATEWAY_BASE_URL, "username": "mobile", "password": ""},
    )
    device, _ = HikDevice.objects.get_or_create(
        tenant=tenant,
        dev_index=MOBILE_DEV_INDEX,
        defaults={
            "gateway": gateway,
            "kind": HikDevice.KIND_MOBILE_VIRTUAL,
            "serial_number": MOBILE_DEV_INDEX,
            "device_name": "Pointage mobile",
            "status": "online",
            "protocol_type": "mobile",
        },
    )
    return device


def record_mobile_punch(*, employee, decision, attempt, idempotency_key: str,
                        client_reported_at=None, app_version: str = "", mocked=None):
    """Écrit RawEvent + AttendanceLog pour un pointage mobile accepté.

    Idempotence : dedupe_key = mobile:{tenant}:{employee}:{idempotency_key}.
    Un retry réseau (même clé) renvoie le pointage existant, marqué
    ``created=False`` — l'appelant renvoie alors la même réponse de succès.
    L'heure OFFICIELLE est l'heure serveur ; client_reported_at n'est que de la
    métadonnée de diagnostic.
    """
    from django.db import IntegrityError
    from django.utils import timezone as dj_timezone

    from hik_gateway.models import AttendanceLog, RawEvent

    server_now = dj_timezone.now()
    device = get_mobile_device(employee.tenant)
    dedupe_key = f"mobile:{employee.tenant_id}:{employee.id}:{idempotency_key}"

    clock_drift_seconds = None
    if client_reported_at is not None:
        clock_drift_seconds = round((client_reported_at - server_now).total_seconds(), 1)

    payload = {
        "source": "mobile",
        "latitude": attempt.latitude,
        "longitude": attempt.longitude,
        "accuracy_m": attempt.accuracy_m,
        "site_id": decision.site.id,
        "site_name": decision.site.name,
        "distance_m": decision.distance_m,
        "tolerance_m": decision.tolerance_m,
        "zone": decision.zone,
        "idempotency_key": idempotency_key,
        "server_received_at": server_now.isoformat(),
        "client_reported_at": client_reported_at.isoformat() if client_reported_at else None,
        "clock_drift_seconds": clock_drift_seconds,
        "app_version": app_version or None,
        "mocked": mocked,
    }

    try:
        with transaction.atomic():
            raw_event = RawEvent.objects.create(
                tenant=employee.tenant,
                device=device,
                dev_index=MOBILE_DEV_INDEX,
                event_type="MobilePunchEvent",
                event_datetime=server_now,
                employee_no=employee.employee_no,
                employee_no_string=employee.employee_no,
                attendance_status=decision.action,
                dedupe_key=dedupe_key,
                payload=payload,
            )
            log = AttendanceLog.objects.create(
                tenant=employee.tenant,
                employee=employee,
                person_id=employee.employee_no,
                device=device,
                timestamp=server_now,
                attendance_type="mobile",
                attendance_status=decision.action,
                normalized_action=decision.action,
                direction="IN" if decision.action == "CHECK_IN" else "OUT",
                source=AttendanceLog.SOURCE_MOBILE,
                raw_event=raw_event,
            )
        return log, True
    except IntegrityError:
        existing = RawEvent.objects.filter(dedupe_key=dedupe_key).first()
        if existing is not None and hasattr(existing, "attendance_log"):
            return existing.attendance_log, False
        raise
