"""
Management command: create_demo_tenant
Creates a fully activated demo tenant HQ-CASA with an admin user for local testing.
Usage: python manage.py create_demo_tenant
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()

TENANT_CODE        = "HQ-CASA"
TENANT_NAME        = "HQ Casa (Demo)"
ORG_NAME           = "Siège"
ADMIN_EMAIL        = "admin@hq-casa.test"
ADMIN_PASSWORD     = "Admin@2024"
ADMIN_USERNAME     = "admin_hq"
OPERATOR_EMAIL     = "operator@hq-casa.test"
OPERATOR_PASSWORD  = "Oper@2024"
OPERATOR_USERNAME  = "operator_hq"


class Command(BaseCommand):
    help = "Creates the HQ-CASA demo tenant with admin + operator accounts."

    def handle(self, *args, **options):
        from tenants.models import Tenant, TenantMembership, TenantRole, PaymentStatus
        from employees.models import Organization, OrganizationMembership, OrganizationRole

        with transaction.atomic():
            # ── Tenant ────────────────────────────────────────────────
            tenant, t_created = Tenant.objects.get_or_create(
                code=TENANT_CODE,
                defaults={
                    "name": TENANT_NAME,
                    "is_active": True,
                    "payment_status": PaymentStatus.ACTIVE
                    if hasattr(PaymentStatus, "ACTIVE")
                    else "active",
                },
            )
            if not t_created:
                tenant.is_active = True
                try:
                    tenant.payment_status = (
                        PaymentStatus.ACTIVE
                        if hasattr(PaymentStatus, "ACTIVE")
                        else "active"
                    )
                except Exception:
                    pass
                tenant.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"{'Created' if t_created else 'Found'} tenant: {tenant.code}"
                )
            )

            # ── Default organisation ───────────────────────────────────
            org, o_created = Organization.objects.get_or_create(
                tenant=tenant,
                code="SIEGE",
                defaults={"name": ORG_NAME, "is_active": True},
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"{'Created' if o_created else 'Found'} organisation: {org.name}"
                )
            )

            # ── Admin user ─────────────────────────────────────────────
            admin, a_created = User.objects.get_or_create(
                email=ADMIN_EMAIL,
                defaults={
                    "username": ADMIN_USERNAME,
                    "is_active": True,
                    "is_staff": True,
                },
            )
            admin.set_password(ADMIN_PASSWORD)
            admin.is_active = True
            admin.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"{'Created' if a_created else 'Updated'} admin: {ADMIN_EMAIL}"
                )
            )

            # Tenant membership — TENANT_ADMIN
            TenantMembership.objects.get_or_create(
                user=admin,
                tenant=tenant,
                defaults={"role": TenantRole.TENANT_ADMIN},
            )

            # Org membership — ORG_ADMIN
            OrganizationMembership.objects.get_or_create(
                user=admin,
                organization=org,
                defaults={"role": OrganizationRole.ORG_ADMIN},
            )

            # ── Operator user ──────────────────────────────────────────
            op, op_created = User.objects.get_or_create(
                email=OPERATOR_EMAIL,
                defaults={
                    "username": OPERATOR_USERNAME,
                    "is_active": True,
                    "is_staff": False,
                },
            )
            op.set_password(OPERATOR_PASSWORD)
            op.is_active = True
            op.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"{'Created' if op_created else 'Updated'} operator: {OPERATOR_EMAIL}"
                )
            )

            TenantMembership.objects.get_or_create(
                user=op,
                tenant=tenant,
                defaults={"role": TenantRole.OPERATOR
                          if hasattr(TenantRole, "OPERATOR") else TenantRole.TENANT_ADMIN},
            )
            OrganizationMembership.objects.get_or_create(
                user=op,
                organization=org,
                defaults={"role": OrganizationRole.OPERATOR
                          if hasattr(OrganizationRole, "OPERATOR") else OrganizationRole.ORG_ADMIN},
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 54))
        self.stdout.write(self.style.SUCCESS("  DEMO TENANT PRÊT"))
        self.stdout.write(self.style.SUCCESS("=" * 54))
        self.stdout.write(f"  Tenant code : {TENANT_CODE}")
        self.stdout.write(f"  Admin       : {ADMIN_EMAIL}  /  {ADMIN_PASSWORD}")
        self.stdout.write(f"  Opérateur   : {OPERATOR_EMAIL}  /  {OPERATOR_PASSWORD}")
        self.stdout.write(self.style.SUCCESS("=" * 54))
        self.stdout.write("")
