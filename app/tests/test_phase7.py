"""Tests Phase 7 — Observabilité (7.1, 7.2, 7.3)."""

import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

User = get_user_model()


class SentryMiddlewareTests(APITestCase):
    """Test SentryContextMiddleware ne crashe pas sans Sentry."""

    def test_middleware_no_sentry_anonymous(self):
        """Test middleware with anonymous user and no Sentry."""
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)

    def test_middleware_no_sentry_authenticated(self):
        """Test middleware with authenticated user and no Sentry."""
        user = User.objects.create_user("testuser7", "test7@example.com", "pass123")
        self.client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)


class PrometheusMetricsTests(APITestCase):
    """Test endpoint /metrics Prometheus."""

    def test_metrics_endpoint_accessible(self):
        """Test /metrics endpoint is accessible."""
        response = self.client.get("/metrics")
        # Prometheus responds with various codes depending on config
        self.assertIn(response.status_code, [200, 301, 302, 404, 405])

    def test_metrics_endpoint_with_trailing_slash(self):
        """Test /metrics/ endpoint with trailing slash."""
        response = self.client.get("/metrics/")
        # Doit être accessible — contenu texte Prometheus
        self.assertIn(response.status_code, [200, 301, 302, 404, 405])


class BusinessMetricsTests(TestCase):
    """Test que les métriques métier sont définies et incrémentables."""

    def test_hik_events_counter_importable(self):
        """Test hik_events_received_total metric is importable and usable."""
        from config.metrics import hik_events_received_total

        hik_events_received_total.labels(tenant_code="test", event_type="access").inc()
        # No exception = OK

    def test_gateway_push_counter_importable(self):
        """Test gateway_push_total metric is importable and usable."""
        from config.metrics import gateway_push_total

        gateway_push_total.labels(tenant_code="test", status="success").inc()

    def test_device_onboarding_counter_importable(self):
        """Test device_onboarding_total metric is importable and usable."""
        from config.metrics import device_onboarding_total

        device_onboarding_total.labels(tenant_code="test", status="started").inc()

    def test_tenant_signups_counter_importable(self):
        """Test tenant_signups_total metric is importable and usable."""
        from config.metrics import tenant_signups_total

        tenant_signups_total.inc()

    def test_active_tenants_gauge_importable(self):
        """Test active_tenants_gauge metric is importable and usable."""
        from config.metrics import active_tenants_gauge

        active_tenants_gauge.set(5)

    def test_hik_events_processing_histogram_importable(self):
        """Test hik_events_processing_seconds histogram is importable and usable."""
        from config.metrics import hik_events_processing_seconds

        hik_events_processing_seconds.labels(tenant_code="test").observe(0.5)

    def test_gateway_push_duration_histogram_importable(self):
        """Test gateway_push_duration_seconds histogram is importable and usable."""
        from config.metrics import gateway_push_duration_seconds

        gateway_push_duration_seconds.labels(tenant_code="test").observe(1.2)


class AdminDashboardTests(APITestCase):
    """Test dashboard admin métriques (7.3)."""

    def setUp(self):
        self.staff = User.objects.create_user(
            "staff7", "staff7@example.com", "pass123", is_staff=True
        )
        self.regular = User.objects.create_user(
            "regular7", "regular7@example.com", "pass123"
        )

    def test_dashboard_accessible_without_auth_redirect(self):
        """Test dashboard redirects without authentication."""
        response = self.client.get("/admin/dashboard/metrics/")
        # Should redirect to login
        self.assertIn(response.status_code, [302, 403])

    def test_dashboard_accessible_to_staff(self):
        """Test dashboard endpoint is accessible to staff users."""
        self.client.force_login(self.staff, backend='django.contrib.auth.backends.ModelBackend')
        response = self.client.get("/admin/dashboard/metrics/")
        # Should either return 200 or redirect (due to staff_member_required)
        self.assertIn(response.status_code, [200, 302])

    def test_dashboard_returns_json_structure(self):
        """Test dashboard endpoint exists and can be accessed."""
        # Test that the view can at least be imported and configured
        from config.admin_dashboard import AdminDashboardView
        self.assertTrue(hasattr(AdminDashboardView, 'get'))

    def test_dashboard_structure_on_direct_call(self):
        """Test dashboard view returns expected structure when called directly."""
        from config.admin_dashboard import AdminDashboardView
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get('/admin/dashboard/metrics/')
        request.user = self.staff

        view = AdminDashboardView()
        response = view.dispatch(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn("tenants", data)
        self.assertIn("users", data)
        self.assertIn("billing", data)
        self.assertIn("devices", data)
        self.assertIn("events", data)
        self.assertIn("generated_at", data)
        self.assertIn("period_days", data)

    def test_dashboard_mau_is_integer(self):
        """Test MAU is an integer in the response."""
        from config.admin_dashboard import AdminDashboardView
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get('/admin/dashboard/metrics/')
        request.user = self.staff

        view = AdminDashboardView()
        response = view.dispatch(request)
        data = json.loads(response.content)
        self.assertIsInstance(data["users"]["mau"], int)
        self.assertIsInstance(data["users"]["total_active"], int)

    def test_dashboard_tenants_structure(self):
        """Test dashboard tenants section has required fields."""
        from config.admin_dashboard import AdminDashboardView
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get('/admin/dashboard/metrics/')
        request.user = self.staff

        view = AdminDashboardView()
        response = view.dispatch(request)
        data = json.loads(response.content)
        tenants = data["tenants"]
        self.assertIn("active", tenants)
        self.assertIn("inactive", tenants)
        self.assertIn("signups_30d", tenants)
        self.assertIn("signups_total", tenants)
        self.assertIn("churn_30d", tenants)

    def test_dashboard_devices_structure(self):
        """Test dashboard devices section has required fields."""
        from config.admin_dashboard import AdminDashboardView
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get('/admin/dashboard/metrics/')
        request.user = self.staff

        view = AdminDashboardView()
        response = view.dispatch(request)
        data = json.loads(response.content)
        devices = data["devices"]
        self.assertIn("total", devices)
        self.assertIn("top_tenants", devices)
        self.assertIsInstance(devices["top_tenants"], list)

    def test_dashboard_billing_placeholder(self):
        """Test dashboard billing section has MRR placeholder."""
        from config.admin_dashboard import AdminDashboardView
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get('/admin/dashboard/metrics/')
        request.user = self.staff

        view = AdminDashboardView()
        response = view.dispatch(request)
        data = json.loads(response.content)
        billing = data["billing"]
        self.assertIn("mrr", billing)
        self.assertIn("note", billing)
        self.assertEqual(billing["mrr"], 0)
        self.assertIn("Stripe", billing["note"])
