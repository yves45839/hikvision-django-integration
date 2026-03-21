from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0007_deviceonboardingjob_deviceorganizationbinding"),
        ("employees", "0015_organizationinvitation_organizationmembership"),
    ]

    operations = [
        migrations.AddField(
            model_name="department",
            name="devices",
            field=models.ManyToManyField(blank=True, related_name="departments", to="devices.device"),
        ),
        migrations.AddField(
            model_name="employee",
            name="device_assignment_mode",
            field=models.CharField(
                choices=[
                    ("employee_only", "Employee only"),
                    ("department_only", "Department only"),
                    ("combined", "Combined"),
                ],
                default="combined",
                max_length=24,
            ),
        ),
    ]
