"""Billing API endpoints — subscriptions, one-time payments, customer portal,
and the Stripe webhook receiver.

All endpoints (except the webhook) require an authenticated user and scope
data to the user's active tenant.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Invoice, Payment, Plan, Subscription
from .permissions import assert_can_manage_billing, get_request_tenant
from .serializers import (
    CreateCheckoutOneTimeInput,
    CreateCheckoutSubscriptionInput,
    CreatePaymentIntentInput,
    CreatePortalInput,
    InvoiceSerializer,
    PaymentSerializer,
    PlanSerializer,
    SubscriptionSerializer,
)
from .services import (
    create_billing_portal_session,
    create_checkout_session_one_time,
    create_checkout_session_subscription,
    create_payment_intent,
)
from .webhooks import process_event

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public catalog (read-only)
# ---------------------------------------------------------------------------

class PlanViewSet(viewsets.ReadOnlyModelViewSet):
    """List / retrieve active plans. Read-only for clients — admin-only writes
    happen via Django admin or `manage.py` commands.

    Supports filtering by currency:
        GET /api/billing/plans/?currency=eur

    The frontend pricing page uses this for the multi-currency selector
    (one Stripe Price per currency, same `code` reused across them).
    """

    serializer_class = PlanSerializer
    permission_classes = [AllowAny]
    lookup_field = "code"

    def get_queryset(self):
        qs = Plan.objects.filter(is_active=True).order_by("sort_order", "amount")
        currency = self.request.query_params.get("currency")
        if currency:
            qs = qs.filter(currency__iexact=currency.strip())
        return qs

    @action(detail=False, methods=["get"], url_path="currencies", permission_classes=[AllowAny])
    def currencies(self, request):
        """List the distinct currencies available across active plans."""
        codes = (
            Plan.objects.filter(is_active=True)
            .values_list("currency", flat=True)
            .distinct()
            .order_by("currency")
        )
        return Response(sorted({(c or "").lower() for c in codes if c}))


# ---------------------------------------------------------------------------
# Tenant-scoped: subscriptions, invoices, payments
# ---------------------------------------------------------------------------

class SubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_request_tenant(self.request)
        return (
            Subscription.objects
            .select_related("plan", "customer")
            .filter(tenant=tenant)
            .order_by("-created_at")
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Cancel at period end (does not refund the current period)."""
        subscription = self.get_object()
        assert_can_manage_billing(request, subscription.tenant)
        from .services.stripe_client import get_stripe

        stripe = get_stripe()
        stripe.Subscription.modify(
            subscription.stripe_subscription_id,
            cancel_at_period_end=True,
        )
        subscription.cancel_at_period_end = True
        subscription.save(update_fields=["cancel_at_period_end", "updated_at"])
        return Response(self.get_serializer(subscription).data)

    @action(detail=True, methods=["post"], url_path="resume")
    def resume(self, request, pk=None):
        """Undo a pending cancellation (only valid before period end)."""
        subscription = self.get_object()
        assert_can_manage_billing(request, subscription.tenant)
        from .services.stripe_client import get_stripe

        stripe = get_stripe()
        stripe.Subscription.modify(
            subscription.stripe_subscription_id,
            cancel_at_period_end=False,
        )
        subscription.cancel_at_period_end = False
        subscription.save(update_fields=["cancel_at_period_end", "updated_at"])
        return Response(self.get_serializer(subscription).data)


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_request_tenant(self.request)
        return Invoice.objects.filter(tenant=tenant).order_by("-created_at")


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_request_tenant(self.request)
        return Payment.objects.filter(tenant=tenant).order_by("-created_at")


# ---------------------------------------------------------------------------
# Action endpoints (POST-only)
# ---------------------------------------------------------------------------

class CreateCheckoutSubscriptionView(APIView):
    """POST /api/billing/checkout/subscription/ — returns a Stripe Checkout URL."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant = assert_can_manage_billing(request)
        data = CreateCheckoutSubscriptionInput(data=request.data)
        data.is_valid(raise_exception=True)
        cleaned = data.validated_data

        plan = Plan.objects.filter(code=cleaned["plan_code"], is_active=True).first()
        if not plan:
            return Response(
                {"detail": f"Unknown or inactive plan: {cleaned['plan_code']}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            session = create_checkout_session_subscription(
                tenant=tenant,
                plan=plan,
                user_email=request.user.email,
                trial_period_days=cleaned.get("trial_period_days"),
                success_url=cleaned.get("success_url") or None,
                cancel_url=cleaned.get("cancel_url") or None,
            )
        except Exception as exc:
            logger.exception("Stripe checkout (subscription) failed")
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(
            {
                "session_id": session["id"],
                "url": session.get("url"),
                "publishable_key": getattr(settings, "STRIPE_PUBLISHABLE_KEY", ""),
            },
            status=status.HTTP_201_CREATED,
        )


class CreateCheckoutOneTimeView(APIView):
    """POST /api/billing/checkout/one-time/ — hosted Checkout for a single payment."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant = assert_can_manage_billing(request)
        data = CreateCheckoutOneTimeInput(data=request.data)
        data.is_valid(raise_exception=True)
        cleaned = data.validated_data

        try:
            session = create_checkout_session_one_time(
                tenant=tenant,
                amount_cents=cleaned["amount_cents"],
                currency=cleaned.get("currency", "eur"),
                description=cleaned.get("description", ""),
                user_email=request.user.email,
                success_url=cleaned.get("success_url") or None,
                cancel_url=cleaned.get("cancel_url") or None,
            )
        except Exception as exc:
            logger.exception("Stripe checkout (one-time) failed")
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(
            {
                "session_id": session["id"],
                "url": session.get("url"),
                "publishable_key": getattr(settings, "STRIPE_PUBLISHABLE_KEY", ""),
            },
            status=status.HTTP_201_CREATED,
        )


class CreatePaymentIntentView(APIView):
    """POST /api/billing/payment-intent/ — for embedded Stripe Elements flows.

    Returns a `client_secret` that the frontend uses with Stripe Elements
    (Payment Element) to confirm the payment without leaving the app.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant = assert_can_manage_billing(request)
        data = CreatePaymentIntentInput(data=request.data)
        data.is_valid(raise_exception=True)
        cleaned = data.validated_data

        try:
            payment = create_payment_intent(
                tenant=tenant,
                amount_cents=cleaned["amount_cents"],
                currency=cleaned.get("currency", "eur"),
                description=cleaned.get("description", ""),
                user=request.user,
                metadata=cleaned.get("metadata") or {},
            )
        except Exception as exc:
            logger.exception("Stripe PaymentIntent creation failed")
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(
            {
                "payment_id": payment.id,
                "stripe_payment_intent_id": payment.stripe_payment_intent_id,
                "client_secret": getattr(payment, "client_secret", ""),
                "amount": str(payment.amount),
                "currency": payment.currency,
                "publishable_key": getattr(settings, "STRIPE_PUBLISHABLE_KEY", ""),
            },
            status=status.HTTP_201_CREATED,
        )


class CreatePortalView(APIView):
    """POST /api/billing/portal/ — return a URL to the Stripe Billing Portal."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant = assert_can_manage_billing(request)
        data = CreatePortalInput(data=request.data)
        data.is_valid(raise_exception=True)

        try:
            session = create_billing_portal_session(
                tenant=tenant,
                return_url=data.validated_data.get("return_url") or None,
            )
        except Exception as exc:
            logger.exception("Stripe billing portal session failed")
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({"url": session["url"]}, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Webhook receiver
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(APIView):
    """POST /api/billing/webhook/

    Receives Stripe webhooks. Verifies the signature using STRIPE_WEBHOOK_SECRET
    (configure this in Stripe dashboard or via `stripe listen --forward-to ...`).
    """
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request):
        from .services.stripe_client import get_stripe

        secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        payload = request.body

        try:
            stripe = get_stripe()
        except Exception:
            return HttpResponse(status=503)

        try:
            if secret:
                event = stripe.Webhook.construct_event(payload, sig_header, secret)
            else:
                # Dev / no-signature mode — still parse JSON but log a warning.
                logger.warning("STRIPE_WEBHOOK_SECRET not set — skipping signature check.")
                import json

                event = json.loads(payload.decode("utf-8"))
        except (ValueError, stripe.error.SignatureVerificationError) as exc:  # type: ignore[attr-defined]
            logger.warning("Invalid Stripe webhook signature: %s", exc)
            return HttpResponse(status=400)
        except Exception:
            logger.exception("Unable to parse Stripe webhook payload")
            return HttpResponse(status=400)

        try:
            process_event(event)
        except Exception:
            # We've already logged inside process_event; tell Stripe to retry.
            return HttpResponse(status=500)

        return HttpResponse(status=200)


# ---------------------------------------------------------------------------
# Convenience: current tenant billing summary
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def billing_summary(request):
    tenant = get_request_tenant(request)
    sub = (
        Subscription.objects
        .select_related("plan")
        .filter(tenant=tenant)
        .order_by("-created_at")
        .first()
    )
    return Response(
        {
            "tenant": {
                "id": tenant.id,
                "code": tenant.code,
                "name": tenant.name,
                "payment_status": tenant.payment_status,
                "device_quota": tenant.device_quota,
            },
            "subscription": SubscriptionSerializer(sub).data if sub else None,
            "open_invoices": InvoiceSerializer(
                Invoice.objects.filter(tenant=tenant, status="open").order_by("-created_at"),
                many=True,
            ).data,
            "publishable_key": getattr(settings, "STRIPE_PUBLISHABLE_KEY", ""),
        }
    )
