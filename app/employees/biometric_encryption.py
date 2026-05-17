"""
PHASE 6.6 — Chiffrement des données biométriques (RGPD)
Utilise le système Fernet pour chiffrer les données sensibles (empreintes, visages, etc.)
"""
from cryptography.fernet import Fernet
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def _get_cipher_suite() -> Fernet:
    """Récupère la suite de chiffrement Fernet."""
    key = getattr(settings, "ENCRYPTION_KEY", None)
    if not key:
        # Mode développement: générer une clé par défaut
        key = Fernet.generate_key()
        logger.warning("No ENCRYPTION_KEY configured, using generated key (dev only)")
    return Fernet(key)


def encrypt_biometric(data: str) -> str:
    """
    Chiffre des données biométriques (empreinte digitale, reconnaissance faciale, etc.)

    Args:
        data: Données en clair à chiffrer

    Returns:
        Données chiffrées en format base64 UTF-8
    """
    if not data:
        return data

    try:
        cipher = _get_cipher_suite()
        encrypted = cipher.encrypt(data.encode("utf-8"))
        return encrypted.decode("utf-8")
    except Exception as exc:
        logger.error(f"Failed to encrypt biometric data: {exc}")
        raise


def decrypt_biometric(data: str) -> str:
    """
    Déchiffre des données biométriques.

    Args:
        data: Données chiffrées en format base64 UTF-8

    Returns:
        Données en clair
    """
    if not data:
        return data

    try:
        cipher = _get_cipher_suite()
        decrypted = cipher.decrypt(data.encode("utf-8"))
        return decrypted.decode("utf-8")
    except Exception as exc:
        logger.error(f"Failed to decrypt biometric data: {exc}")
        raise


def is_encrypted(data: str) -> bool:
    """
    Vérifie si une donnée semble déjà chiffrée (heuristique).

    Args:
        data: Donnée à vérifier

    Returns:
        True si probablement chiffrée
    """
    if not data:
        return False
    # Les données Fernet chiffrées commencent par "gAAAAAB"
    return data.startswith("gAAAAAB")
