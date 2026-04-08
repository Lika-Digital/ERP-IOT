"""Application settings loaded from environment variables / .env file."""
import logging
import secrets
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

_config_logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql://erp_user:erp_password@localhost:5432/erp_iot"

    # ── App server ────────────────────────────────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # ── CORS ──────────────────────────────────────────────────────────────────
    allowed_origins: str = "http://localhost:5173"

    # ── JWT ───────────────────────────────────────────────────────────────────
    jwt_secret: Optional[str] = None
    jwt_expire_minutes: int = 480  # 8 hours

    # ── Seeding ───────────────────────────────────────────────────────────────
    default_admin_email: str = "admin@erp-iot.local"
    default_admin_password: Optional[str] = None

    # ── Pedestal API ──────────────────────────────────────────────────────────
    pedestal_api_timeout_seconds: int = 10
    pedestal_api_max_retries: int = 3

    # ── Service account password encryption ──────────────────────────────────
    # Fernet key — generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    erp_encryption_key: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

# ── JWT secret resolution ─────────────────────────────────────────────────────
if settings.jwt_secret is None:
    settings.jwt_secret = secrets.token_hex(32)
    _config_logger.critical(
        "SECURITY WARNING: JWT_SECRET is not set. A random secret was generated — "
        "all sessions will be invalidated on every restart. "
        "Set JWT_SECRET in your .env file."
    )

# ── Admin password check ──────────────────────────────────────────────────────
if settings.default_admin_password is None:
    _config_logger.warning(
        "DEFAULT_ADMIN_PASSWORD is not set. Default super_admin will NOT be seeded. "
        "Set DEFAULT_ADMIN_PASSWORD in your .env file."
    )

# ── Encryption key check ──────────────────────────────────────────────────────
if settings.erp_encryption_key is None:
    _config_logger.warning(
        "ERP_ENCRYPTION_KEY is not set. Service account password encryption will fail. "
        "Generate with: python -c \"from cryptography.fernet import Fernet; "
        "print(Fernet.generate_key().decode())\""
    )
