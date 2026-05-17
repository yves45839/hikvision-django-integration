"""Add a free-form ``features`` JSON field on Plan for the FeatureGate.

The frontend's ``<FeatureGate feature="...">`` component checks this dict
to decide whether to render premium content or an UpgradeWall.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0002_plan_trial_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="features",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text=(
                    "Feature flags for this plan. Used by the frontend "
                    "FeatureGate component."
                ),
            ),
        ),
    ]
