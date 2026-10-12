"""Application settings loaded from environment variables / .env file."""
import logging
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

_config_logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────────
    # No default: a default URL is a default password (spec §11 O16).
    database_url: Optional[str] = None

    # ── App server ────────────────────────────────────────────────────────────
    # 127.0.0.1, ne 0.0.0.0: nginx je jedini javni slusatelj (spec §8.1).
    # 0.0.0.0 je bio jedini medium nalaz bandita u repou (B104).
    app_host: str = "127.0.0.1"
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


class MissingSecretError(RuntimeError):
    """Podizanje je odbijeno jer obvezna tajna nije postavljena."""


settings = Settings()

def _is_blank(value: str | None) -> bool:
    """None i prazan string su oboje 'nije postavljeno'.

    `.env.example` nosi `JWT_SECRET=` s praznom vrijednoscu (spec §8.3), pa bi
    provjera samo na None propustila tocno onaj slucaj zbog kojeg postoji:
    nekoga ko je kopirao primjer i nije ga popunio.
    """
    return value is None or not value.strip()


# ── JWT secret: FAIL-FAST ─────────────────────────────────────────────────────
# Prije faze 1 ovdje se generirala slucajna tajna i upisao CRITICAL u log.
# Posljedica: svaki restart nevaljanim cini sve sesije, a log nitko ne gleda —
# tiha degradacija sigurnosti. Spec §7.1: podizanje se odbija.
if _is_blank(settings.jwt_secret):
    raise MissingSecretError(
        "JWT_SECRET nije postavljen. Aplikacija se nece dici.\n"
        "  Razvoj:     dodaj JWT_SECRET u backend/.env\n"
        "  Produkcija: systemd LoadCredential (spec 8.3), nikad u datoteku uz aplikaciju\n"
        "  Generiraj:  python -c \"import secrets; print(secrets.token_hex(32))\""
    )

# ── Database URL: FAIL-FAST ───────────────────────────────────────────────────
# Do O16 je zadani URL nosio lozinku (`erp_password`), a alembic.ini drugu
# (javnu). Sada postoji jedan izvor — DATABASE_URL iz okruzenja ili .env — i
# bez njega se nista ne dize, ni aplikacija ni migracija.
if _is_blank(settings.database_url):
    raise MissingSecretError(
        "DATABASE_URL nije postavljen. Aplikacija se nece dici.\n"
        "  Razvoj:     dodaj DATABASE_URL u backend/.env\n"
        "  Produkcija: systemd LoadCredential (spec 8.3), nikad u datoteku uz aplikaciju"
    )

# ── Admin password check ──────────────────────────────────────────────────────
if _is_blank(settings.default_admin_password):
    _config_logger.warning(
        "DEFAULT_ADMIN_PASSWORD is not set. Default super_admin will NOT be seeded. "
        "Set DEFAULT_ADMIN_PASSWORD in your .env file."
    )

# ── Encryption key check ──────────────────────────────────────────────────────
if _is_blank(settings.erp_encryption_key):
    _config_logger.warning(
        "ERP_ENCRYPTION_KEY is not set. Service account password encryption will fail. "
        "Generate with: python -c \"from cryptography.fernet import Fernet; "
        "print(Fernet.generate_key().decode())\""
    )
