"""Add trial configuration to Plan (frictionless trials without card)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="trial_period_days",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Free trial length in days. 0 disables the trial.",
            ),
        ),
        migrations.AddField(
            model_name="plan",
            name="trial_requires_card",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "If False and trial_period_days > 0, Stripe Checkout will set "
                    "payment_method_collection='if_required' so the card is optional."
                ),
            ),
        ),
    ]
