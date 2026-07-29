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
