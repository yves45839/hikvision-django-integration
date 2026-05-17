"""
Tests pour PHASE 6 — Conformité RGPD
"""
import io
import json
import zipfile

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from tenants.models import Tenant, TenantMembership, TenantRole, ConsentLog

User = get_user_model()


class UserDataExportTestCase(TestCase):
    """Tests pour l'export de données (Art. 20)"""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            code="test-tenant",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="SecurePass123!",
        )
        TenantMembership.objects.create(
            user=self.user,
            tenant=self.tenant,
            role=TenantRole.TENANT_ADMIN,
        )

    def test_export_requires_authentication(self):
        """L'export nécessite une authentification"""
        response = self.client.get("/api/auth/me/export/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_export_returns_zip_file(self):
        """L'export retourne un fichier ZIP valide"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/auth/me/export/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn("Content-Disposition", response)

        # Vérifier le contenu du ZIP
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            files = zf.namelist()
            self.assertIn("user_data.json", files)
            self.assertIn("user_data.csv", files)

            # Vérifier le JSON
            with zf.open("user_data.json") as f:
                data = json.load(f)
                self.assertEqual(data["user"]["email"], "test@example.com")
                self.assertEqual(data["user"]["username"], "testuser")
                self.assertIn("export_date", data)
                self.assertIn("tenant_memberships", data)


class UserDeleteTestCase(TestCase):
    """Tests pour l'effacement de compte (Art. 17)"""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            code="test-tenant",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="SecurePass123!",
        )
        TenantMembership.objects.create(
            user=self.user,
            tenant=self.tenant,
            role=TenantRole.TENANT_ADMIN,
        )

    def test_delete_requires_authentication(self):
        """La suppression nécessite une authentification"""
        response = self.client.delete("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_delete_requires_confirmation(self):
        """La suppression nécessite une confirmation explicite"""
        self.client.force_authenticate(user=self.user)
        response = self.client.delete("/api/auth/me/", data={})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("warning", response.data)

    def test_delete_anonymizes_user(self):
        """La suppression anonymise l'utilisateur"""
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(
            "/api/auth/me/",
            data={"confirm": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Vérifier que l'utilisateur est anonymisé
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertTrue(self.user.email.startswith("deleted_"))
        self.assertEqual(self.user.first_name, "")
        self.assertEqual(self.user.last_name, "")


class ConsentLogTestCase(TestCase):
    """Tests pour le journal des consentements"""

    def test_consent_log_creation(self):
        """Test de création d'un ConsentLog"""
        consent = ConsentLog.objects.create(
            email="user@example.com",
            consent_tos=True,
            consent_privacy=True,
            consent_marketing=False,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )

        self.assertEqual(consent.email, "user@example.com")
        self.assertTrue(consent.consent_tos)
        self.assertTrue(consent.consent_privacy)
        self.assertFalse(consent.consent_marketing)
        self.assertIsNotNone(consent.created_at)

    def test_consent_log_without_user(self):
        """ConsentLog peut exister sans utilisateur (user anonymisé)"""
        user = User.objects.create_user(username="user1", email="user@example.com")
        consent = ConsentLog.objects.create(
            user=user,
            email="user@example.com",
            consent_tos=True,
            consent_privacy=True,
        )

        self.assertEqual(consent.user_id, user.id)

        # Supprimer l'utilisateur - ConsentLog reste
        user.delete()
        consent.refresh_from_db()
        self.assertIsNone(consent.user)
        self.assertEqual(consent.email, "user@example.com")


class LegalPagesTestCase(TestCase):
    """Tests pour les pages légales"""

    def test_terms_of_service(self):
        """Test endpoint TOS"""
        response = self.client.get("/legal/tos/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("title", data)
        self.assertIn("content", data)
        self.assertEqual(data["title"], "Conditions Générales d'Utilisation")

    def test_privacy_policy(self):
        """Test endpoint Privacy Policy"""
        response = self.client.get("/legal/privacy/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("title", data)
        self.assertIn("content", data)
        self.assertEqual(data["title"], "Politique de Confidentialité")


class DPADownloadTestCase(TestCase):
    """Tests pour le téléchargement du DPA"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="SecurePass123!",
        )

    def test_dpa_requires_authentication(self):
        """Le DPA nécessite une authentification"""
        response = self.client.get("/api/auth/dpa/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_dpa_download(self):
        """Test du téléchargement du DPA"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/auth/dpa/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn("Content-Disposition", response)
        self.assertIn("DPA_SecurePoint", response["Content-Disposition"])

        # Vérifier le contenu
        content = response.content.decode("utf-8")
        self.assertIn("DATA PROCESSING AGREEMENT", content)
        self.assertIn(self.user.email, content)
