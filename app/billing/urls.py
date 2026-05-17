"""URL routing for the billing app — mounted under `/api/billing/`."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CreateCheckoutOneTimeView,
    CreateCheckoutSubscriptionView,
    CreatePaymentIntentView,
    CreatePortalView,
    InvoiceViewSet,
    PaymentViewSet,
    PlanViewSet,
    StripeWebhookView,
    SubscriptionViewSet,
    billing_summary,
)


router = DefaultRouter()
router.register(r"plans", PlanViewSet, basename="billing-plans")
router.register(r"subscriptions", SubscriptionViewSet, basename="billing-subscriptions")
router.register(r"invoices", InvoiceViewSet, basename="billing-invoices")
router.register(r"payments", PaymentViewSet, basename="billing-payments")


urlpatterns = [
    path("", include(router.urls)),
    path("summary/", billing_summary, name="billing-summary"),
    path("checkout/subscription/", CreateCheckoutSubscriptionView.as_view(), name="billing-checkout-subscription"),
    path("checkout/one-time/", CreateCheckoutOneTimeView.as_view(), name="billing-checkout-one-time"),
    path("payment-intent/", CreatePaymentIntentView.as_view(), name="billing-payment-intent"),
    path("portal/", CreatePortalView.as_view(), name="billing-portal"),
    path("webhook/", StripeWebhookView.as_view(), name="billing-webhook"),
]
