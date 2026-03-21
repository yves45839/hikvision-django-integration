from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("employees", "0004_alter_employeeattribute_value"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="last_gateway_push_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="employee",
            name="needs_gateway_push",
            field=models.BooleanField(default=True),
        ),
        migrations.AddIndex(
            model_name="employee",
            index=models.Index(fields=["tenant", "needs_gateway_push"], name="employees_em_tenant__44cc20_idx"),
        ),
    ]
