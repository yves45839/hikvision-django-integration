from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("hik_gateway", "0006_attendancecorrection"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AttendanceCorrectionLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("work_date", models.DateField()),
                ("action", models.CharField(choices=[("CREATE", "Create"), ("UPDATE", "Update")], max_length=16)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="attendance_correction_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "correction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_logs",
                        to="hik_gateway.attendancecorrection",
                    ),
                ),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attendance_correction_logs",
                        to="employees.employee",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attendance_correction_logs",
                        to="tenants.tenant",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="attendancecorrectionlog",
            index=models.Index(
                fields=["tenant", "employee", "work_date"],
                name="hik_gateway_tenant__a88c5e_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="attendancecorrectionlog",
            index=models.Index(fields=["tenant", "created_at"], name="hik_gateway_tenant__f57101_idx"),
        ),
    ]
