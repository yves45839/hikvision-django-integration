from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("employees", "0008_employee_planning_and_daily_slots"),
        ("hik_gateway", "0003_rename_idx_hik_rawevent_dev_door_reader_idx_hik_access_dev_door_reader"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendancelog",
            name="employee",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="hik_attendance_logs",
                to="employees.employee",
            ),
        ),
    ]
