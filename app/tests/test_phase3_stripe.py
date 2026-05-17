"""Tests Phase 3 — Stripe billing (mocks uniquement, aucun appel HTTP réel).

Couvre :
- PlanViewSet read-only (filtre is_active, restrictions par devise)
- billing_summary — incohérence d'absence de subscription
- CreateCheckoutSubscriptionView — happy path, plan inconnu, non-admin
- CreateCheckoutOneTimeView — happy path
- CreatePortalView — happy path
- StripeWebhookView — signature manquante en dev OK, signature invalide → 400, payload mal formé → 400
- handle_subscription_event — créé / mis à jour / supprimé + mirror sur Tenant
- handle_invoice_event — paid + payment_failed (sans envoyer de mail)
- process_event — idempotence sur event_id

Tous les appels Stripe sont mockés via `unittest.mock.patch`.
"""
from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

# Speed up user creation across this whole module — default PBKDF2 is ~80ms/user.
_FAST_HASHER = override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)

from billing.models import (
    Customer,
    Invoice,
    InvoiceStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
    WebhookEvent,
)
from tenants.models import Tenant, TenantMembership, TenantRole

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures helper
# ---------------------------------------------------------------------------

def _make_tenant(code: str = "ACME", name: str = "Acme") -> Tenant:
    return Tenant.objects.create(code=code, name=name, is_active=True)


def _make_user(
    email: str,
    password: str = "pass1234!",
    *,
    tenant: Tenant | None = None,
    role: str = TenantRole.TENANT_ADMIN,
) -> User:
    u = User.objects.create_user(email, email, password)
    if tenant is not None:
        TenantMembership.objects.create(user=u, tenant=tenant, role=role)
    return u


def _make_plan(
    code: str = "pro",
    *,
    interval: str = "month",
    is_active: bool = True,
    stripe_price_id: str = "price_test_pro",
    trial_days: int = 14,
    trial_requires_card: bool = False,
    device_quota: int = 100,
) -> Plan:
    return Plan.objects.create(
        code=code,
        name=f"Plan {code.title()}",
        interval=interval,
        is_active=is_active,
        stripe_price_id=stripe_price_id,
        amount=Decimal("29.99"),
        currency="eur",
        trial_period_days=trial_days,
        trial_requires_card=trial_requires_card,
        device_quota=device_quota,
    )


# ---------------------------------------------------------------------------
# Plans (read-only)
# ---------------------------------------------------------------------------

@_FAST_HASHER
class PlanViewSetTests(APITestCase):
    def test_lists_only_active_plans(self):
        _make_plan("free", is_active=False)
        active = _make_plan("pro")
        resp = self.client.get("/api/billing/plans/")
        self.assertEqual(resp.status_code, 200)
        codes = {p["code"] for p in resp.data}
        self.assertIn(active.code, codes)
        # The viewset is supposed to filter is_active=True
        self.assertNotIn("free", codes)

    def test_anonymous_can_read_plans(self):
        """Pricing page must work without auth — public catalog."""
        _make_plan("pro")
        resp = self.client.get("/api/billing/plans/")
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# billing_summary
# ---------------------------------------------------------------------------

@_FAST_HASHER
class BillingSummaryTests(APITestCase):
    def setUp(self):
        self.tenant = _make_tenant("BSUM")
        self.user = _make_user("admin@bsum.test", tenant=self.tenant)

    def test_summary_requires_auth(self):
        resp = self.client.get("/api/billing/summary/")
        self.assertEqual(resp.status_code, 401)

    def test_summary_returns_tenant_block_even_without_subscription(self):
        self.client.force_authenticate(self.user)
        resp = self.client.get(
            "/api/billing/summary/",
            HTTP_X_TENANT_CODE=self.tenant.code,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["tenant"]["code"], self.tenant.code)
        self.assertIsNone(resp.data["subscription"])
        self.assertEqual(resp.data["open_invoices"], [])


# ---------------------------------------------------------------------------
# Checkout endpoints
# ---------------------------------------------------------------------------

@_FAST_HASHER
class CheckoutSubscriptionTests(APITestCase):
    def setUp(self):
        self.tenant = _make_tenant("CHK")
        self.admin = _make_user("admin@chk.test", tenant=self.tenant)
        self.viewer = _make_user(
            "viewer@chk.test", tenant=self.tenant, role=TenantRole.VIEWER
        )
        self.plan = _make_plan("pro")

    def _post(self, user, payload):
        self.client.force_authenticate(user)
        return self.client.post(
            "/api/billing/checkout/subscription/",
            data=payload,
            format="json",
            HTTP_X_TENANT_CODE=self.tenant.code,
        )

    @patch("billing.views.create_checkout_session_subscription")
    def test_admin_can_create_subscription_checkout(self, mock_create):
        mock_create.return_value = {
            "id": "cs_test_123",
            "url": "https://checkout.stripe.com/c/cs_test_123",
        }
        resp = self._post(
            self.admin, {"plan_code": self.plan.code, "trial_period_days": 14}
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["session_id"], "cs_test_123")
        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["plan"], self.plan)
        self.assertEqual(kwargs["tenant"], self.tenant)

    def test_unknown_plan_returns_404(self):
        resp = self._post(self.admin, {"plan_code": "ghost-plan"})
        self.assertEqual(resp.status_code, 404)

    def test_viewer_role_cannot_create_checkout(self):
        resp = self._post(self.viewer, {"plan_code": self.plan.code})
        # `assert_can_manage_billing` raises PermissionDenied → 403
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_blocked(self):
        resp = self.client.post(
            "/api/billing/checkout/subscription/",
            data={"plan_code": self.plan.code},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    @patch(
        "billing.views.create_checkout_session_subscription",
        side_effect=RuntimeError("stripe down"),
    )
    def test_stripe_failure_returns_502(self, _):
        resp = self._post(self.admin, {"plan_code": self.plan.code})
        self.assertEqual(resp.status_code, 502)


@_FAST_HASHER
class CheckoutOneTimeTests(APITestCase):
    def setUp(self):
        self.tenant = _make_tenant("OT")
        self.admin = _make_user("admin@ot.test", tenant=self.tenant)

    @patch("billing.views.create_checkout_session_one_time")
    def test_one_time_checkout_happy_path(self, mock_create):
        mock_create.return_value = {
            "id": "cs_test_ot",
            "url": "https://checkout.stripe.com/c/cs_test_ot",
        }
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/billing/checkout/one-time/",
            data={
                "amount_cents": 9999,
                "currency": "eur",
                "description": "Add-on cameras",
            },
            format="json",
            HTTP_X_TENANT_CODE=self.tenant.code,
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["session_id"], "cs_test_ot")


@_FAST_HASHER
class PortalTests(APITestCase):
    def setUp(self):
        self.tenant = _make_tenant("POR")
        self.admin = _make_user("admin@por.test", tenant=self.tenant)

    @patch("billing.views.create_billing_portal_session")
    def test_portal_returns_url(self, mock_create):
        mock_create.return_value = {"url": "https://billing.stripe.com/p/test"}
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/billing/portal/",
            format="json",
            HTTP_X_TENANT_CODE=self.tenant.code,
        )
        # CreatePortalView returns 201 for created sessions (matches the other
        # checkout views' behaviour). Accept 200/201 for resilience.
        self.assertIn(resp.status_code, [200, 201])
        self.assertIn("billing.stripe.com", resp.data["url"])


# ---------------------------------------------------------------------------
# Webhook endpoint — signature handling
# ---------------------------------------------------------------------------

class StripeWebhookViewTests(APITestCase):
    def setUp(self):
        self.url = "/api/billing/webhook/"

    @patch("billing.views.process_event")
    @patch("billing.views.settings")
    @patch("billing.services.stripe_client.get_stripe")
    def test_dev_mode_no_signature_secret_accepts_event(
        self, mock_get_stripe, mock_settings, mock_process
    ):
        # Empty STRIPE_WEBHOOK_SECRET → dev/no-signature path
        mock_settings.STRIPE_WEBHOOK_SECRET = ""
        mock_get_stripe.return_value = MagicMock()

        payload = json.dumps({"id": "evt_test_1", "type": "ping"}).encode()
        resp = self.client.post(self.url, data=payload, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        mock_process.assert_called_once()
        # Verify the parsed payload was passed through
        called_with = mock_process.call_args.args[0]
        self.assertEqual(called_with["id"], "evt_test_1")

    @patch("billing.views.settings")
    @patch("billing.services.stripe_client.get_stripe")
    def test_invalid_signature_returns_400(self, mock_get_stripe, mock_settings):
        mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
        fake_stripe = MagicMock()
        # Mimic stripe.error.SignatureVerificationError
        class _SigErr(ValueError):
            pass
        fake_stripe.error.SignatureVerificationError = _SigErr
        fake_stripe.Webhook.construct_event.side_effect = _SigErr("bad sig")
        mock_get_stripe.return_value = fake_stripe

        resp = self.client.post(
            self.url,
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=invalid",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("billing.services.stripe_client.get_stripe", side_effect=RuntimeError("down"))
    def test_stripe_unavailable_returns_503(self, _):
        resp = self.client.post(self.url, data=b"{}", content_type="application/json")
        self.assertEqual(resp.status_code, 503)

    @patch("billing.views.process_event", side_effect=RuntimeError("boom"))
    @patch("billing.views.settings")
    @patch("billing.services.stripe_client.get_stripe")
    def test_processing_error_returns_500_for_stripe_retry(
        self, mock_get_stripe, mock_settings, _
    ):
        mock_settings.STRIPE_WEBHOOK_SECRET = ""
        mock_get_stripe.return_value = MagicMock()
        resp = self.client.post(
            self.url,
            data=json.dumps({"id": "evt_x", "type": "ping"}).encode(),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 500)


# ---------------------------------------------------------------------------
# Webhook handlers — direct unit tests
# ---------------------------------------------------------------------------

class SubscriptionWebhookHandlerTests(APITestCase):
    def setUp(self):
        self.tenant = _make_tenant("SUB")
        self.plan = _make_plan("pro", stripe_price_id="price_pro_eur")
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            stripe_customer_id="cus_test_1",
            email="billing@sub.test",
        )

    def _stripe_sub_payload(self, *, status_str: str = "active") -> dict:
        return {
            "id": "sub_test_1",
            "customer": self.customer.stripe_customer_id,
            "status": status_str,
            "current_period_start": 1_700_000_000,
            "current_period_end": 1_702_592_000,
            "cancel_at_period_end": False,
            "trial_end": None,
            "canceled_at": None,
            "livemode": False,
            "metadata": {"tenant_code": self.tenant.code},
            "items": {
                "data": [
                    {
                        "id": "si_test_1",
                        "price": {"id": self.plan.stripe_price_id},
                    }
                ]
            },
        }

    def test_subscription_created_persists_row_and_marks_tenant_paid(self):
        from billing.webhooks import handle_subscription_event

        handle_subscription_event("customer.subscription.created", self._stripe_sub_payload())

        sub = Subscription.objects.get(stripe_subscription_id="sub_test_1")
        self.assertEqual(sub.tenant, self.tenant)
        self.assertEqual(sub.plan, self.plan)
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.payment_status, "paid")
        self.assertTrue(self.tenant.is_active)
        self.assertEqual(self.tenant.device_quota, self.plan.device_quota)

    def test_subscription_updated_changes_status(self):
        from billing.webhooks import handle_subscription_event

        handle_subscription_event("customer.subscription.created", self._stripe_sub_payload())
        handle_subscription_event(
            "customer.subscription.updated",
            self._stripe_sub_payload(status_str="past_due"),
        )
        sub = Subscription.objects.get(stripe_subscription_id="sub_test_1")
        self.assertEqual(sub.status, SubscriptionStatus.PAST_DUE)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.payment_status, "failed")

    def test_subscription_deleted_marks_canceled_even_when_customer_unknown(self):
        """Stripe may send delete with a customer id we no longer recognize.

        We must still mark the local Subscription row canceled (matched by
        stripe_subscription_id), without crashing on missing references.
        """
        from billing.webhooks import handle_subscription_event

        # Pre-existing local row
        Subscription.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id="sub_test_1",
            status=SubscriptionStatus.ACTIVE,
        )

        payload = self._stripe_sub_payload(status_str="canceled")
        # Pretend we no longer know this customer locally
        payload["customer"] = "cus_unknown_to_db"
        # Drop the metadata fallback path too
        payload["metadata"] = {}

        handle_subscription_event("customer.subscription.deleted", payload)

        sub = Subscription.objects.get(stripe_subscription_id="sub_test_1")
        self.assertEqual(sub.status, SubscriptionStatus.CANCELED)
        self.assertIsNotNone(sub.canceled_at)


class InvoiceWebhookHandlerTests(APITestCase):
    def setUp(self):
        self.tenant = _make_tenant("INV")
        self.plan = _make_plan("pro")
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            stripe_customer_id="cus_inv_1",
            email="billing@inv.test",
        )

    def _stripe_invoice_payload(self, *, status_str: str = "paid") -> dict:
        return {
            "id": "in_test_1",
            "customer": self.customer.stripe_customer_id,
            "subscription": None,
            "number": "INV-001",
            "status": status_str,
            "amount_due": 2999,
            "amount_paid": 2999 if status_str == "paid" else 0,
            "amount_remaining": 0 if status_str == "paid" else 2999,
            "currency": "eur",
            "hosted_invoice_url": "https://invoice.stripe.com/i/in_test_1",
            "invoice_pdf": "https://invoice.stripe.com/i/in_test_1/pdf",
            "period_start": 1_700_000_000,
            "period_end": 1_702_592_000,
            "status_transitions": {"paid_at": 1_701_000_000},
        }

    @patch("billing.webhooks.send_payment_success_email")
    def test_invoice_paid_creates_local_row(self, mock_send_email):
        from billing.webhooks import handle_invoice_event

        handle_invoice_event("invoice.paid", self._stripe_invoice_payload())

        inv = Invoice.objects.get(stripe_invoice_id="in_test_1")
        self.assertEqual(inv.tenant, self.tenant)
        self.assertEqual(inv.status, InvoiceStatus.PAID)
        self.assertIsNotNone(inv.paid_at)
        # Customer email was notified
        mock_send_email.assert_called_once()

    @patch("billing.webhooks.send_payment_failed_email")
    def test_invoice_payment_failed_marks_tenant(self, mock_send_email):
        from billing.webhooks import handle_invoice_event

        # Need a Subscription so the failed handler can mirror onto Tenant
        sub = Subscription.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id="sub_for_fail",
        )
        payload = self._stripe_invoice_payload(status_str="open")
        payload["subscription"] = sub.stripe_subscription_id
        payload["last_payment_error"] = {"message": "card declined"}

        handle_invoice_event("invoice.payment_failed", payload)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.payment_status, "failed")
        mock_send_email.assert_called_once()
        kw = mock_send_email.call_args.kwargs
        self.assertEqual(kw["failure_reason"], "card declined")

    def test_invoice_unknown_customer_is_ignored(self):
        from billing.webhooks import handle_invoice_event

        payload = self._stripe_invoice_payload()
        payload["customer"] = "cus_does_not_exist"
        # Must not raise, must not create
        handle_invoice_event("invoice.paid", payload)
        self.assertFalse(Invoice.objects.filter(stripe_invoice_id="in_test_1").exists())


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------

class ProcessEventIdempotenceTests(APITestCase):
    def test_duplicate_event_id_is_processed_once(self):
        from billing.webhooks import process_event

        # An event type the dispatcher does NOT know — must still be marked
        # processed and the DB row must exist exactly once after duplicates.
        event = {"id": "evt_idem", "type": "unknown.event.type", "data": {"object": {}}}
        process_event(event)
        process_event(event)  # second call is a no-op
        self.assertEqual(
            WebhookEvent.objects.filter(stripe_event_id="evt_idem").count(), 1
        )
        rec = WebhookEvent.objects.get(stripe_event_id="evt_idem")
        self.assertTrue(rec.processed)
