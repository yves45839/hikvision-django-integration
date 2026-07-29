"""Tests for Phase 1 — Infra production."""

from django.test import TestCase, Client, override_settings
from django.conf import settings
from unittest.mock import patch
from rest_framework.test import APITestCase


class TestHealthCheckEndpoint(APITestCase):
    """1.3: Test health check endpoint."""

    def setUp(self):
        """Set up test client."""
        self.client = Client()

    def test_health_endpoint_returns_200(self):
        """Test that /health/ returns 200 when database is healthy."""
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"ok", response.content)
        self.assertIn(b"db", response.content)

    def test_health_endpoint_returns_json(self):
        """Test that /health/ returns valid JSON."""
        response = self.client.get("/health/")
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertIn("status", data)
        self.assertIn("db", data)

    @patch("config.health_views.connection.ensure_connection")
    def test_health_endpoint_returns_503_when_db_down(self, mock_ensure):
        """Test that /health/ returns 503 when database is down."""
        from django.db.utils import OperationalError

        mock_ensure.side_effect = OperationalError("DB is down")
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual(data["status"], "degraded")
        self.assertEqual(data["db"], "error")

    def test_health_endpoint_accessible_without_auth(self):
        """Test that /health/ is accessible without authentication."""
        response = self.client.get("/health/")
        self.assertIn(response.status_code, [200, 503])


class TestReadinessCheckEndpoint(APITestCase):
    """1.3: Test readiness check endpoint."""

    def setUp(self):
        """Set up test client."""
        self.client = Client()

    def test_ready_endpoint_returns_200(self):
        """Test that /ready/ returns 200."""
        response = self.client.get("/ready/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ready")

    def test_ready_endpoint_returns_json(self):
        """Test that /ready/ returns valid JSON."""
        response = self.client.get("/ready/")
        self.assertEqual(response["Content-Type"], "application/json")

    def test_ready_endpoint_accessible_without_auth(self):
        """Test that /ready/ is accessible without authentication."""
        response = self.client.get("/ready/")
        self.assertEqual(response.status_code, 200)


class TestLoggingConfiguration(TestCase):
    """1.4: Test logging configuration."""

    def test_logging_configured(self):
        """Test that LOGGING is configured."""
        self.assertIn("LOGGING", dir(settings))
        logging_config = settings.LOGGING
        self.assertIsNotNone(logging_config)
        self.assertEqual(logging_config["version"], 1)

    def test_logging_has_console_handler(self):
        """Test that logging has console handler."""
        logging_config = settings.LOGGING
        self.assertIn("handlers", logging_config)
        self.assertIn("console", logging_config["handlers"])

    def test_logging_formatters_configured(self):
        """Test that logging formatters are configured."""
        logging_config = settings.LOGGING
        self.assertIn("formatters", logging_config)
        formatters = logging_config["formatters"]
        self.assertIn("json", formatters)
        self.assertIn("verbose", formatters)

    def test_root_logger_configured(self):
        """Test that root logger is configured."""
        logging_config = settings.LOGGING
        self.assertIn("root", logging_config)
        root = logging_config["root"]
        self.assertIn("handlers", root)
        self.assertIn("level", root)

    def test_django_logger_configured(self):
        """Test that django logger is configured."""
        logging_config = settings.LOGGING
        self.assertIn("loggers", logging_config)
        loggers = logging_config["loggers"]
        self.assertIn("django", loggers)

    def test_log_level_from_env(self):
        """Test that LOG_LEVEL is read from environment."""
        logging_config = settings.LOGGING
        log_level = logging_config["root"]["level"]
        self.assertIn(log_level, ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])


class TestStaticFilesConfiguration(TestCase):
    """1.2: Test static files configuration."""

    def test_static_root_configured(self):
        """Test that STATIC_ROOT is configured."""
        self.assertTrue(hasattr(settings, "STATIC_ROOT"))
        self.assertIsNotNone(settings.STATIC_ROOT)

    def test_static_url_configured(self):
        """Test that STATIC_URL is configured."""
        self.assertTrue(hasattr(settings, "STATIC_URL"))
        # Django normalizes static URL to have leading slash
        self.assertIn(settings.STATIC_URL, ["/static/", "static/"])

    def test_whitenoise_middleware_installed(self):
        """Test that whitenoise middleware is installed."""
        self.assertIn(
            "whitenoise.middleware.WhiteNoiseMiddleware",
            settings.MIDDLEWARE,
        )


class TestSentryConfiguration(TestCase):
    """1.4: Test Sentry configuration (optional)."""

    def test_sentry_dsn_configured(self):
        """Test that SENTRY_DSN can be configured."""
        self.assertTrue(hasattr(settings, "SENTRY_DSN"))
        self.assertIsInstance(settings.SENTRY_DSN, str)

    def test_sentry_sdk_in_requirements(self):
        """Test that sentry-sdk is in requirements."""
        import os
        requirements_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "requirements.txt"
        )
        if os.path.exists(requirements_path):
            with open(requirements_path, "r") as f:
                content = f.read()
                self.assertIn("sentry-sdk", content)


class TestGunicornConfiguration(TestCase):
    """1.1: Test that gunicorn is in requirements."""

    def test_gunicorn_in_requirements(self):
        """Test that gunicorn is in requirements.txt."""
        import os
        requirements_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "requirements.txt"
        )
        with open(requirements_path, "r") as f:
            content = f.read()
            self.assertIn("gunicorn", content)


class TestDockerfileExists(TestCase):
    """1.1: Test that multi-stage Dockerfile exists."""

    def test_dockerfile_exists(self):
        """Test that Dockerfile exists."""
        import os
        dockerfile_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "Dockerfile"
        )
        self.assertTrue(os.path.exists(dockerfile_path))

    def test_dockerfile_multi_stage(self):
        """Test that Dockerfile uses multi-stage build."""
        import os
        dockerfile_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "Dockerfile"
        )
        with open(dockerfile_path, "r") as f:
            content = f.read()
            self.assertIn("AS builder", content)
            self.assertIn("AS production", content)
            self.assertIn("appuser", content)

    def test_dockerfile_has_healthcheck(self):
        """Test that Dockerfile has HEALTHCHECK."""
        import os
        dockerfile_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "Dockerfile"
        )
        with open(dockerfile_path, "r") as f:
            content = f.read()
            self.assertIn("HEALTHCHECK", content)


class TestDockerComposeHasRedis(TestCase):
    """1.1 (révisé 2026-07-29) : plus de Redis — broker/cache = Postgres.

    La décision d'architecture (STATUS.md §2) remplace Redis par le cache
    DatabaseCache et Django-Q2 (broker ORM). Ce test verrouille l'absence
    de Redis pour éviter sa réintroduction accidentelle.
    """

    def test_docker_compose_exists(self):
        """Test that docker-compose.yml exists."""
        import os
        compose_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docker-compose.yml"
        )
        self.assertTrue(os.path.exists(compose_path))

    def test_docker_compose_has_no_redis(self):
        """Le compose de dev ne doit plus déclarer de service Redis."""
        import os
        compose_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docker-compose.yml"
        )
        with open(compose_path, "r") as f:
            content = f.read()
            self.assertNotIn("redis", content.lower())

    def test_settings_use_orm_broker_for_tasks(self):
        """Django-Q2 doit utiliser la base de données comme broker."""
        from django.conf import settings
        self.assertEqual(settings.Q_CLUSTER.get("orm"), "default")
        self.assertIn("django_q", settings.INSTALLED_APPS)

    def test_docker_compose_healthchecks(self):
        """Test that docker-compose services have healthchecks."""
        import os
        compose_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docker-compose.yml"
        )
        with open(compose_path, "r") as f:
            content = f.read()
            self.assertIn("healthcheck", content)


class TestEnvironmentConfiguration(TestCase):
    """1.4: Test environment configuration."""

    def test_log_level_in_env_example(self):
        """Test that LOG_LEVEL is in .env.example."""
        import os
        env_example_path = os.path.join(
            os.path.dirname(__file__), "..", "..", ".env.example"
        )
        with open(env_example_path, "r") as f:
            content = f.read()
            self.assertIn("LOG_LEVEL", content)

    def test_sentry_dsn_in_env_example(self):
        """Test that SENTRY_DSN is in .env.example."""
        import os
        env_example_path = os.path.join(
            os.path.dirname(__file__), "..", "..", ".env.example"
        )
        with open(env_example_path, "r") as f:
            content = f.read()
            self.assertIn("SENTRY_DSN", content)
