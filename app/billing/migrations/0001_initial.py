"""Initial migration for the billing app — Stripe-backed subscriptions, payments, usage."""
from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ---------- Plan ----------
        migrations.CreateModel(
            name="Plan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=64, unique=True, help_text="basic, pro, enterprise, ...")),
                ("name", models.CharField(max_length=128)),
                ("description", models.TextField(blank=True, default="")),
                ("stripe_product_id", models.CharField(max_length=255, blank=True, default="")),
                ("stripe_price_id", models.CharField(max_length=255, blank=True, default="")),
                ("amount", models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))),
                ("currency", models.CharField(max_length=8, default="eur")),
                ("interval", models.CharField(
                    max_length=16,
                    default="month",
                    choices=[("month", "Mensuel"), ("year", "Annuel"), ("one_time", "Paiement unique")],
                )),
                ("device_quota", models.PositiveIntegerField(default=10)),
                ("event_quota_per_month", models.PositiveIntegerField(default=10000)),
                ("has_priority_support", models.BooleanField(default=False)),
                ("has_advanced_analytics", models.BooleanField(default=False)),
                ("is_metered", models.BooleanField(default=False)),
                ("metered_unit_label", models.CharField(blank=True, default="", max_length=64)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("sort_order", "amount"),
                "indexes": [
                    models.Index(fields=["is_active", "sort_order"], name="billing_pla_is_acti_5bd2bb_idx"),
                    models.Index(fields=["stripe_price_id"], name="billing_pla_stripe__7ba7ab_idx"),
                ],
            },
        ),
        # ---------- Customer ----------
        migrations.CreateModel(
            name="Customer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stripe_customer_id", models.CharField(max_length=255, unique=True)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("name", models.CharField(blank=True, default="", max_length=255)),
                ("default_payment_method_id", models.CharField(blank=True, default="", max_length=255)),
                ("livemode", models.BooleanField(default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="billing_customer",
                    to="tenants.tenant",
                )),
            ],
            options={
                "indexes": [
                    models.Index(fields=["stripe_customer_id"], name="billing_cus_stripe__9c7e2a_idx"),
                ],
            },
        ),
        # ---------- Subscription ----------
        migrations.CreateModel(
            name="Subscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stripe_subscription_id", models.CharField(max_length=255, unique=True)),
                ("stripe_subscription_item_id", models.CharField(blank=True, default="", max_length=255)),
                ("status", models.CharField(
                    max_length=32,
                    default="incomplete",
                    choices=[
                        ("incomplete", "Incomplete"),
                        ("incomplete_expired", "Incomplete expired"),
                        ("trialing", "Trialing"),
                        ("active", "Active"),
                        ("past_due", "Past due"),
                        ("canceled", "Canceled"),
                        ("unpaid", "Unpaid"),
                        ("paused", "Paused"),
                    ],
                )),
                ("current_period_start", models.DateTimeField(blank=True, null=True)),
                ("current_period_end", models.DateTimeField(blank=True, null=True)),
                ("trial_end", models.DateTimeField(blank=True, null=True)),
                ("cancel_at_period_end", models.BooleanField(default=False)),
                ("canceled_at", models.DateTimeField(blank=True, null=True)),
                ("livemode", models.BooleanField(default=False)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("customer", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="subscriptions",
                    to="billing.customer",
                )),
                ("plan", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="subscriptions",
                    to="billing.plan",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="subscriptions",
                    to="tenants.tenant",
                )),
            ],
            options={
                "ordering": ("-created_at",),
                "indexes": [
                    models.Index(fields=["tenant", "status"], name="billing_sub_tenant__a31b88_idx"),
                    models.Index(fields=["status", "current_period_end"], name="billing_sub_status_b9dc1f_idx"),
                ],
            },
        ),
        # ---------- Invoice ----------
        migrations.CreateModel(
            name="Invoice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stripe_invoice_id", models.CharField(max_length=255, unique=True)),
                ("number", models.CharField(blank=True, default="", max_length=64)),
                ("status", models.CharField(
                    max_length=32,
                    default="draft",
                    choices=[
                        ("draft", "Draft"),
                        ("open", "Open"),
                        ("paid", "Paid"),
                        ("uncollectible", "Uncollectible"),
                        ("void", "Void"),
                    ],
                )),
                ("amount_due", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("amount_paid", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("amount_remaining", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("currency", models.CharField(default="eur", max_length=8)),
                ("hosted_invoice_url", models.URLField(blank=True, default="")),
                ("invoice_pdf", models.URLField(blank=True, default="")),
                ("period_start", models.DateTimeField(blank=True, null=True)),
                ("period_end", models.DateTimeField(blank=True, null=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("customer", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="invoices",
                    to="billing.customer",
                )),
                ("subscription", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="invoices",
                    to="billing.subscription",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="invoices",
                    to="tenants.tenant",
                )),
            ],
            options={
                "ordering": ("-created_at",),
                "indexes": [
                    models.Index(fields=["tenant", "status"], name="billing_inv_tenant__c41a12_idx"),
                    models.Index(fields=["customer", "-created_at"], name="billing_inv_custome_d7c333_idx"),
                ],
            },
        ),
        # ---------- Payment ----------
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stripe_payment_intent_id", models.CharField(max_length=255, unique=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(default="eur", max_length=8)),
                ("status", models.CharField(
                    max_length=32,
                    default="requires_payment_method",
                    choices=[
                        ("requires_payment_method", "Requires payment method"),
                        ("requires_confirmation", "Requires confirmation"),
                        ("requires_action", "Requires action"),
                        ("processing", "Processing"),
                        ("succeeded", "Succeeded"),
                        ("requires_capture", "Requires capture"),
                        ("canceled", "Canceled"),
                    ],
                )),
                ("description", models.CharField(blank=True, default="", max_length=255)),
                ("receipt_url", models.URLField(blank=True, default="")),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="initiated_payments",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("customer", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="payments",
                    to="billing.customer",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="payments",
                    to="tenants.tenant",
                )),
            ],
            options={
                "ordering": ("-created_at",),
                "indexes": [
                    models.Index(fields=["tenant", "status"], name="billing_pay_tenant__e6cb55_idx"),
                    models.Index(fields=["status", "-created_at"], name="billing_pay_status_f81d44_idx"),
                ],
            },
        ),
        # ---------- UsageRecord ----------
        migrations.CreateModel(
            name="UsageRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stripe_usage_record_id", models.CharField(blank=True, default="", max_length=255)),
                ("stripe_subscription_item_id", models.CharField(max_length=255)),
                ("quantity", models.PositiveIntegerField()),
                ("timestamp", models.DateTimeField()),
                ("action", models.CharField(default="increment", max_length=16)),
                ("idempotency_key", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("subscription", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="usage_records",
                    to="billing.subscription",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="usage_records",
                    to="tenants.tenant",
                )),
            ],
            options={
                "ordering": ("-timestamp",),
                "indexes": [
                    models.Index(fields=["tenant", "-timestamp"], name="billing_usa_tenant__16a288_idx"),
                    models.Index(fields=["subscription", "-timestamp"], name="billing_usa_subscri_2bf977_idx"),
                ],
            },
        ),
        # ---------- WebhookEvent ----------
        migrations.CreateModel(
            name="WebhookEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stripe_event_id", models.CharField(max_length=255, unique=True)),
                ("type", models.CharField(db_index=True, max_length=128)),
                ("livemode", models.BooleanField(default=False)),
                ("payload", models.JSONField()),
                ("processed", models.BooleanField(default=False)),
                ("processing_error", models.TextField(blank=True, default="")),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ("-received_at",),
                "indexes": [
                    models.Index(fields=["type", "-received_at"], name="billing_web_type_38de14_idx"),
                    models.Index(fields=["processed", "-received_at"], name="billing_web_process_4a55b8_idx"),
                ],
            },
        ),
    ]
