"""Application settings loaded from environment variables / .env file."""
import logging
import os
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

    # ── Users, 2FA, one-time links (D20, spec §4.9, §7.1) ─────────────────────
    # There is no DEFAULT_ADMIN_PASSWORD: the first admin comes from a one-time
    # link printed by `python -m app.setup_admin` (D20.3).
    public_base_url: str = "http://localhost:5173"   # where the UI is reached; goes into links
    setup_link_minutes: int = 30          # first admin, from the command line
    invite_link_hours: int = 24           # links an Admin issues on the Users screen
    mfa_token_minutes: int = 5            # the token between password and code
    lockout_threshold: int = 5            # failures in a row (password and 2FA add up)
    lockout_minutes: int = 15

    # ── Pedestal API ──────────────────────────────────────────────────────────
    pedestal_api_timeout_seconds: int = 10
    pedestal_api_max_retries: int = 3

    # ── Collector (spec §5.2) — on by default: an ERP that does not collect is broken ──
    # Tests and one-off tools switch it off; production never does.
    collector_enabled: bool = True

    # ── Retention, days (spec §4.7) — one number each ─────────────────────────
    retention_sync_log_days: int = 30
    retention_session_log_days: int = 90
    retention_alarm_log_days: int = 400
    retention_intervals_days: int = 400        # then the monthly aggregate
    retention_command_audit_days: int = 730
    retention_audit_log_days: int = 730        # the older control audit, same weight
    retention_reconciliation_days: int = 90
    retention_cache_days: int = 30             # cache rows nobody refreshed
    retention_auth_audit_days: int = 730       # sign-in evidence, like command_audit
    retention_setup_tokens_days: int = 30      # counted from the link's expiry
    # D21 (spec §13.1): alarms and decoy touches are evidence, like command_audit
    retention_security_alarms_days: int = 730
    retention_decoy_hits_days: int = 730
    retention_service_windows_days: int = 400  # counted from the window's end
    retention_berth_reservations_days: int = 400  # D28; counted from the reservation's end

    # ── Decoys, layer 2 (spec §7.1, D13) — comma-separated; empty = that decoy is off ──
    # Nobody legitimate uses these: a sign-in with a decoy e-mail, or a webhook
    # carrying a decoy key, is recorded in decoy_hits and answered exactly like
    # any other failure. The decoy endpoints are in app/services/decoys.py.
    decoy_account_emails: str = ""
    decoy_api_keys: str = ""

    # ── Webhook receiver ──────────────────────────────────────────────────────
    webhook_max_body_bytes: int = 65536

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
        "JWT_SECRET is not set. The application will not start.\n"
        "  Development: add JWT_SECRET to backend/.env\n"
        "  Production:  systemd LoadCredential (spec 8.3), never a file next to the app\n"
        "  Generate:    python -c \"import secrets; print(secrets.token_hex(32))\""
    )

# ── Database URL: FAIL-FAST ───────────────────────────────────────────────────
# Do O16 je zadani URL nosio lozinku (`erp_password`), a alembic.ini drugu
# (javnu). Sada postoji jedan izvor — DATABASE_URL iz okruzenja ili .env — i
# bez njega se nista ne dize, ni aplikacija ni migracija.
if _is_blank(settings.database_url):
    raise MissingSecretError(
        "DATABASE_URL is not set. The application will not start.\n"
        "  Development: add DATABASE_URL to backend/.env\n"
        "  Production:  systemd LoadCredential (spec 8.3), never a file next to the app"
    )

# ── DEFAULT_ADMIN_PASSWORD is gone (D20.3) ────────────────────────────────────
# A leftover in an old .env is ignored, and said so: nobody should think it
# still creates an account.
if os.environ.get("DEFAULT_ADMIN_PASSWORD") is not None:
    _config_logger.warning(
        "DEFAULT_ADMIN_PASSWORD is set but no longer used (D20): nothing is seeded. "
        "First admin: python -m app.setup_admin --email <e-mail>"
    )

# ── Encryption key check ──────────────────────────────────────────────────────
if _is_blank(settings.erp_encryption_key):
    _config_logger.warning(
        "ERP_ENCRYPTION_KEY is not set. Service account password encryption will fail. "
        "Generate with: python -c \"from cryptography.fernet import Fernet; "
        "print(Fernet.generate_key().decode())\""
    )
