"""
Symmetric encryption for service account passwords stored in the database.

Uses Fernet (AES-128-CBC + HMAC-SHA256).
Key must be a URL-safe base64-encoded 32-byte value — generate with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

The key is loaded from settings.erp_encryption_key.
"""
from cryptography.fernet import Fernet, InvalidToken
from ..config import settings

# Module-level Fernet instance (initialised once, raises on bad key at import time)
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = settings.erp_encryption_key
        if not key:
            raise RuntimeError(
                "ERP_ENCRYPTION_KEY is not set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            )
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_password(plain: str) -> str:
    """Encrypt a plaintext password and return a URL-safe base64 ciphertext string."""
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    """Decrypt a Fernet-encrypted password. Raises InvalidToken if tampered."""
    try:
        return _get_fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt service account password — key mismatch or data corruption") from exc
