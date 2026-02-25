from django.db import migrations, models
import django.db.models.deletion


def set_cursor_tenant(apps, schema_editor):
    DeviceCursor = apps.get_model("hik_gateway", "DeviceCursor")
    for cursor in DeviceCursor.objects.select_related("device").all().iterator():
        cursor.tenant_id = cursor.device.tenant_id
        cursor.save(update_fields=["tenant"])


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0001_initial"),
        ("hik_gateway", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="device",
            name="device_id",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AlterField(
            model_name="device",
            name="dev_index",
            field=models.CharField(max_length=64),
        ),
        migrations.AddConstraint(
            model_name="device",
            constraint=models.UniqueConstraint(
                fields=("tenant", "dev_index"), name="uq_hik_device_tenant_dev_index"
            ),
        ),
        migrations.AddField(
            model_name="rawevent",
            name="attendance_status",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(model_name="rawevent", name="card_no", field=models.CharField(blank=True, default="", max_length=128)),
        migrations.AddField(model_name="rawevent", name="card_reader_no", field=models.IntegerField(blank=True, null=True)),
        migrations.AddField(model_name="rawevent", name="door_no", field=models.IntegerField(blank=True, null=True)),
        migrations.AddField(model_name="rawevent", name="employee_no", field=models.CharField(blank=True, default="", max_length=128)),
        migrations.AddField(model_name="rawevent", name="employee_no_string", field=models.CharField(blank=True, default="", max_length=128)),
        migrations.AddField(model_name="rawevent", name="front_serial_no", field=models.IntegerField(blank=True, null=True)),
        migrations.AddField(model_name="rawevent", name="major_event_type", field=models.IntegerField(blank=True, null=True)),
        migrations.AddField(model_name="rawevent", name="serial_no", field=models.IntegerField(blank=True, null=True)),
        migrations.AddField(model_name="rawevent", name="sub_event_type", field=models.IntegerField(blank=True, null=True)),
        migrations.AddField(model_name="attendancelog", name="attendance_status", field=models.CharField(blank=True, default="", max_length=64)),
        migrations.AddField(model_name="attendancelog", name="direction", field=models.CharField(default="UNKNOWN", max_length=16)),
        migrations.AddField(model_name="devicecursor", name="last_serial_no", field=models.IntegerField(blank=True, null=True)),
        migrations.RenameField(model_name="devicecursor", old_name="last_result_position", new_name="last_search_result_position"),
        migrations.AddField(
            model_name="devicecursor",
            name="tenant",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="hik_device_cursors",
                to="tenants.tenant",
            ),
        ),
        migrations.RunPython(set_cursor_tenant, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="devicecursor",
            name="tenant",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="hik_device_cursors",
                to="tenants.tenant",
            ),
        ),
        migrations.CreateModel(
            name="DeviceReaderConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("door_no", models.IntegerField()),
                ("card_reader_no", models.IntegerField()),
                ("direction_default", models.CharField(choices=[("IN", "In"), ("OUT", "Out")], max_length=8)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reader_configs",
                        to="hik_gateway.device",
                    ),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["device", "door_no", "card_reader_no"])],
            },
        ),
        migrations.AddConstraint(
            model_name="devicereaderconfig",
            constraint=models.UniqueConstraint(fields=("device", "door_no", "card_reader_no"), name="uq_hik_reader_direction"),
        ),
    ]
