"""
PHASE 6.2-6.3 — RGPD: Export données (art. 20) + Effacement (art. 17)
"""
import csv
import datetime
import io
import json
import logging
import uuid
import zipfile

from django.db import transaction
from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
)
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class UserDataExportView(APIView):
    """
    Export RGPD art. 20 — Portabilité des données
    Retourne un ZIP contenant JSON + CSV avec toutes les données de l'utilisateur.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # Collecter les données utilisateur
        data = {
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "date_joined": user.date_joined.isoformat(),
                "last_login": user.last_login.isoformat() if user.last_login else None,
                "is_active": user.is_active,
            },
            "export_date": datetime.datetime.utcnow().isoformat(),
        }

        # Ajouter les memberships tenant
        from tenants.models import TenantMembership
        memberships = TenantMembership.objects.select_related("tenant").filter(user=user)
        data["tenant_memberships"] = [
            {
                "tenant_id": m.tenant_id,
                "tenant_code": m.tenant.code,
                "tenant_name": m.tenant.name,
                "role": m.role,
                "is_primary": m.is_primary,
                "created_at": m.created_at.isoformat(),
            }
            for m in memberships
        ]

        # Ajouter les memberships organisation
        from employees.models import OrganizationMembership
        org_memberships = OrganizationMembership.objects.select_related("organization", "organization__tenant").filter(user=user)
        data["organization_memberships"] = [
            {
                "organization_id": m.organization_id,
                "organization_name": m.organization.name,
                "organization_code": m.organization.code,
                "tenant_code": m.organization.tenant.code,
                "role": m.role,
                "created_at": m.created_at.isoformat(),
            }
            for m in org_memberships
        ]

        # Créer ZIP avec JSON + CSV
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # Ajouter JSON
            zf.writestr(
                "user_data.json",
                json.dumps(data, indent=2, ensure_ascii=False),
            )

            # Ajouter CSV utilisateur
            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow(["Field", "Value"])
            for key, value in data["user"].items():
                writer.writerow([key, value])
            zf.writestr("user_data.csv", csv_buffer.getvalue())

            # Ajouter CSV memberships
            if data["tenant_memberships"]:
                csv_buffer = io.StringIO()
                writer = csv.DictWriter(csv_buffer, fieldnames=data["tenant_memberships"][0].keys())
                writer.writeheader()
                writer.writerows(data["tenant_memberships"])
                zf.writestr("tenant_memberships.csv", csv_buffer.getvalue())

            if data["organization_memberships"]:
                csv_buffer = io.StringIO()
                writer = csv.DictWriter(csv_buffer, fieldnames=data["organization_memberships"][0].keys())
                writer.writeheader()
                writer.writerows(data["organization_memberships"])
                zf.writestr("organization_memberships.csv", csv_buffer.getvalue())

        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="export_rgpd_{user.id}_{datetime.date.today().isoformat()}.zip"'
        return response


class UserDeleteView(APIView):
    """
    Effacement RGPD art. 17 — "Droit à l'oubli"
    Anonymise l'utilisateur sans supprimer pour conserver l'historique.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user
        confirm = request.data.get("confirm", False)

        if not confirm:
            return Response(
                {
                    "warning": "Cette action est irréversible. Envoyez confirm=true pour confirmer.",
                    "consequences": (
                        "Votre compte sera anonymisé et toutes vos données personnelles seront "
                        "supprimées. Seules les références nécessaires à l'audit seront conservées."
                    ),
                },
                status=HTTP_400_BAD_REQUEST,
            )

        # Anonymiser (ne pas supprimer pour garder l'historique des transactions)
        try:
            with transaction.atomic():
                anon_id = str(uuid.uuid4())[:8]
                user.email = f"deleted_{anon_id}@anonymized.invalid"
                user.first_name = ""
                user.last_name = ""
                user.is_active = False
                user.save(update_fields=["email", "first_name", "last_name", "is_active"])

                # Marquer les tokens de vérification comme utilisés
                from tenants.models import EmailVerificationToken, PasswordResetToken
                EmailVerificationToken.objects.filter(user=user, is_used=False).update(
                    is_used=True,
                    used_at=datetime.datetime.now(),
                )
                PasswordResetToken.objects.filter(user=user, is_used=False).update(
                    is_used=True,
                    used_at=datetime.datetime.now(),
                )

                logger.warning(f"User {user.id} anonymized (account deletion requested)")

        except Exception as exc:
            logger.exception(f"Failed to anonymize user {user.id}: {exc}")
            return Response(
                {"detail": f"Erreur lors de l'anonymisation: {exc}"},
                status=HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "status": "account_anonymized",
                "message": "Votre compte a été anonymisé et désactivé. Vos données personnelles ont été supprimées.",
            },
            status=HTTP_200_OK,
        )
