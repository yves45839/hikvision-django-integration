# Generated migration for audit app

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(max_length=100)),
                ('target_model', models.CharField(blank=True, max_length=100)),
                ('target_id', models.CharField(blank=True, max_length=100)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('tenant_code', models.CharField(blank=True, db_index=True, max_length=100)),
                ('extra', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_events_as_actor', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name='auditevent',
            index=models.Index(fields=['tenant_code', 'created_at'], name='audit_audit_tenant__abc123_idx'),
        ),
        migrations.AddIndex(
            model_name='auditevent',
            index=models.Index(fields=['actor', 'created_at'], name='audit_audit_actor_created_idx'),
        ),
    ]
