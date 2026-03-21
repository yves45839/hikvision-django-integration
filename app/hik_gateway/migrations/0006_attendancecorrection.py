from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("employees", "0014_workshift_late_allowable_minutes_and_more"),
        ("hik_gateway", "0005_attendancelog_normalized_action"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AttendanceCorrection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("work_date", models.DateField()),
                ("arrival_time", models.TimeField()),
                ("departure_time", models.TimeField()),
                ("break_start_time", models.TimeField(blank=True, null=True)),
                ("break_end_time", models.TimeField(blank=True, null=True)),
                ("overtime_hours", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_attendance_corrections",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attendance_corrections",
                        to="employees.employee",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attendance_corrections",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="updated_attendance_corrections",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="attendancecorrection",
            constraint=models.UniqueConstraint(
                fields=("tenant", "employee", "work_date"),
                name="uq_hik_attendance_correction_employee_day",
            ),
        ),
        migrations.AddIndex(
            model_name="attendancecorrection",
            index=models.Index(fields=["tenant", "work_date"], name="hik_gateway_tenant__ec96da_idx"),
        ),
        migrations.AddIndex(
            model_name="attendancecorrection",
            index=models.Index(
                fields=["tenant", "employee", "work_date"],
                name="hik_gateway_tenant__68ba79_idx",
            ),
        ),
    ]
