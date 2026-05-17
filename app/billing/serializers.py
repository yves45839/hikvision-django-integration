"""DRF serializers for the billing API."""
from __future__ import annotations

from rest_framework import serializers

from .models import Invoice, Payment, Plan, Subscription, UsageRecord


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = (
            "id",
            "code",
            "name",
            "description",
            "amount",
            "currency",
            "interval",
            "device_quota",
            "event_quota_per_month",
            "has_priority_support",
            "has_advanced_analytics",
            "is_metered",
            "metered_unit_label",
            "trial_period_days",
            "trial_requires_card",
            "features",
            "is_active",
            "sort_order",
        )
        read_only_fields = fields


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = (
            "id",
            "stripe_subscription_id",
            "plan",
            "status",
            "current_period_start",
            "current_period_end",
            "trial_end",
            "cancel_at_period_end",
            "canceled_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = (
            "id",
            "stripe_invoice_id",
            "number",
            "status",
            "amount_due",
            "amount_paid",
            "amount_remaining",
            "currency",
            "hosted_invoice_url",
            "invoice_pdf",
            "period_start",
            "period_end",
            "paid_at",
            "created_at",
        )
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "id",
            "stripe_payment_intent_id",
            "amount",
            "currency",
            "status",
            "description",
            "receipt_url",
            "created_at",
        )
        read_only_fields = fields


class UsageRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageRecord
        fields = (
            "id",
            "subscription",
            "stripe_subscription_item_id",
            "quantity",
            "timestamp",
            "action",
            "created_at",
        )
        read_only_fields = fields


# ---- Action input serializers ----

class CreateCheckoutSubscriptionInput(serializers.Serializer):
    plan_code = serializers.CharField(max_length=64)
    trial_period_days = serializers.IntegerField(required=False, min_value=0, max_value=90)
    success_url = serializers.URLField(required=False, allow_blank=True)
    cancel_url = serializers.URLField(required=False, allow_blank=True)


class CreateCheckoutOneTimeInput(serializers.Serializer):
    amount_cents = serializers.IntegerField(min_value=50)
    currency = serializers.CharField(max_length=8, default="eur")
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    success_url = serializers.URLField(required=False, allow_blank=True)
    cancel_url = serializers.URLField(required=False, allow_blank=True)


class CreatePaymentIntentInput(serializers.Serializer):
    amount_cents = serializers.IntegerField(min_value=50)
    currency = serializers.CharField(max_length=8, default="eur")
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    metadata = serializers.DictField(child=serializers.CharField(), required=False)


class CreatePortalInput(serializers.Serializer):
    return_url = serializers.URLField(required=False, allow_blank=True)
