from pathlib import Path

from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[2]


class DeployEmailConfigurationTests(SimpleTestCase):
    def test_prod_compose_defaults_match_label_ci_smtp_ssl(self):
        compose = (REPO_ROOT / "deploy" / "docker-compose.prod.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("EMAIL_HOST: ${EMAIL_HOST:-mail.label-ci.com}", compose)
        self.assertIn("EMAIL_PORT: ${EMAIL_PORT:-465}", compose)
        self.assertIn("EMAIL_USE_TLS: ${EMAIL_USE_TLS:-false}", compose)
        self.assertIn("EMAIL_USE_SSL: ${EMAIL_USE_SSL:-true}", compose)
        self.assertIn(
            "DEFAULT_FROM_EMAIL: ${DEFAULT_FROM_EMAIL:-noreply@label-ci.com}",
            compose,
        )

    def test_prod_env_example_uses_label_ci_smtp_ssl(self):
        env_example = (REPO_ROOT / "deploy" / ".env.production.example").read_text(
            encoding="utf-8"
        )

        expected_lines = [
            "EMAIL_HOST=mail.label-ci.com",
            "EMAIL_PORT=465",
            "EMAIL_HOST_USER=noreply@label-ci.com",
            "EMAIL_USE_TLS=false",
            "EMAIL_USE_SSL=true",
            "DEFAULT_FROM_EMAIL=noreply@label-ci.com",
        ]
        for line in expected_lines:
            with self.subTest(line=line):
                self.assertIn(line, env_example)
