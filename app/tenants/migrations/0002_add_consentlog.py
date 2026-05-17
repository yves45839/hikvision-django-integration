"""
PHASE 6.4 — Migration pour le modèle ConsentLog (RGPD)
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConsentLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254)),
                ("consent_tos", models.BooleanField(default=False)),
                ("consent_privacy", models.BooleanField(default=False)),
                ("consent_marketing", models.BooleanField(default=False)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="consent_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["email", "created_at"], name="tenants_cons_email_idx"),
                    models.Index(fields=["user", "created_at"], name="tenants_cons_user_idx"),
                ],
            },
        ),
    ]
