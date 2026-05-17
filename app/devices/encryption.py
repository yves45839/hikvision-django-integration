"""0.6: Device credential encryption using Fernet."""

import base64
import os
from cryptography.fernet import Fernet


def get_fernet():
    """Get Fernet cipher instance, using KMS_KEY env or dev fallback."""
    key = os.getenv("KMS_KEY", "")
    if not key:
        # Dev fallback — génère une clé déterministe 32 bytes
        key = base64.urlsafe_b64encode(b"dev-key-32bytes-change-in-prod!!")
    return Fernet(key if isinstance(key, bytes) else key.encode())


def encrypt_value(val: str) -> str:
    """Encrypt a string value using Fernet."""
    if not val:
        return val
    try:
        return get_fernet().encrypt(val.encode()).decode()
    except Exception:
        # Fallback: return raw value if encryption fails
        return val


def decrypt_value(val: str) -> str:
    """Decrypt a string value using Fernet."""
    if not val:
        return val
    try:
        return get_fernet().decrypt(val.encode()).decode()
    except Exception:
        # Return raw value if decryption fails (might be unencrypted)
        return val
