from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hik_gateway", "0007_attendancecorrectionlog"),
    ]

    operations = [
        migrations.AlterField(
            model_name="attendancecorrection",
            name="arrival_time",
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="attendancecorrection",
            name="departure_time",
            field=models.TimeField(blank=True, null=True),
        ),
    ]
