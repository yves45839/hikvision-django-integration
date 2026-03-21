from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hik_gateway", "0004_attendancelog_employee"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendancelog",
            name="normalized_action",
            field=models.CharField(
                choices=[
                    ("CHECK_IN", "Check-in"),
                    ("CHECK_OUT", "Check-out"),
                    ("BREAK_IN", "Break-in"),
                    ("BREAK_OUT", "Break-out"),
                    ("OVERTIME_IN", "Overtime-in"),
                    ("OVERTIME_OUT", "Overtime-out"),
                    ("ACCESS_DENIED", "Access denied"),
                    ("UNKNOWN", "Unknown"),
                ],
                default="UNKNOWN",
                max_length=32,
            ),
        ),
        migrations.AddIndex(
            model_name="attendancelog",
            index=models.Index(fields=["normalized_action"], name="hik_gateway_normali_b31273_idx"),
        ),
    ]
