from django.contrib import admin

from .models import (
    Customer,
    Invoice,
    Payment,
    Plan,
    Subscription,
    UsageRecord,
    WebhookEvent,
)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "amount", "currency", "interval", "is_active", "sort_order")
    list_filter = ("is_active", "interval", "is_metered")
    search_fields = ("code", "name", "stripe_product_id", "stripe_price_id")
    ordering = ("sort_order", "amount")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("tenant", "stripe_customer_id", "email", "livemode", "created_at")
    search_fields = ("stripe_customer_id", "email", "tenant__code", "tenant__name")
    list_filter = ("livemode",)
    autocomplete_fields = ("tenant",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("tenant", "plan", "status", "current_period_end", "cancel_at_period_end", "livemode")
    list_filter = ("status", "livemode", "cancel_at_period_end")
    search_fields = ("stripe_subscription_id", "tenant__code", "tenant__name")
    autocomplete_fields = ("tenant", "customer", "plan")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "tenant", "status", "amount_due", "amount_paid", "currency", "paid_at")
    list_filter = ("status", "currency")
    search_fields = ("stripe_invoice_id", "number", "tenant__code")
    autocomplete_fields = ("tenant", "customer", "subscription")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("tenant", "amount", "currency", "status", "description", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("stripe_payment_intent_id", "description", "tenant__code")
    autocomplete_fields = ("tenant", "customer", "created_by")


@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = ("tenant", "subscription", "quantity", "timestamp", "action")
    list_filter = ("action",)
    search_fields = ("stripe_usage_record_id", "stripe_subscription_item_id", "tenant__code")
    autocomplete_fields = ("tenant", "subscription")


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("stripe_event_id", "type", "processed", "received_at", "processed_at")
    list_filter = ("type", "processed", "livemode")
    search_fields = ("stripe_event_id", "type")
    readonly_fields = ("stripe_event_id", "type", "livemode", "payload", "received_at", "processed_at")
