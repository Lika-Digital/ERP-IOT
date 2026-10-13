"""Users, marina access, 2FA, setup links and the auth audit (spec §4.9, D20)."""
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String,
    Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from ..database import Base
from ..utils.time import utcnow

ROLES = ("admin", "marina_manager")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # D20: two roles. super_admin became admin in migration 010 (spec §5.3).
        CheckConstraint("role IN ('admin', 'marina_manager')", name="ck_users_role"),
        CheckConstraint("failed_count >= 0", name="ck_users_failed_count"),
        # 2FA is confirmed only for a secret that exists
        CheckConstraint("totp_confirmed_at IS NULL OR totp_secret_enc IS NOT NULL",
                        name="ck_users_totp_confirmed_has_secret"),
    )

    id = Column(Integer, primary_key=True)  # the PK is already indexed (spec §11 O17)
    email = Column(String(320), unique=True, nullable=False, index=True)
    # NULL until the user sets it through the one-time link (D20.3)
    password_hash = Column(String(500), nullable=True)
    full_name = Column(String(200), nullable=True)

    # admin (all marinas, all configuration) | marina_manager (assigned marinas, daily work)
    role = Column(String(50), nullable=False, default="marina_manager")

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    last_login = Column(DateTime, nullable=True)

    # ── 2FA (TOTP, RFC 6238) ──────────────────────────────────────────────────
    totp_secret_enc = Column(Text, nullable=True)        # Fernet; NULL until enrolment starts
    totp_confirmed_at = Column(DateTime, nullable=True)  # NULL = only the enrolment screen
    totp_last_step = Column(BigInteger, nullable=True)   # the same code never works twice

    # ── lockout (password and 2FA failures add up) ───────────────────────────
    failed_count = Column(Integer, nullable=False, default=0, server_default="0")
    locked_until = Column(DateTime, nullable=True)

    # Relationships
    marina_access = relationship(
        "UserMarinaAccess",
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="UserMarinaAccess.user_id",
    )


class UserMarinaAccess(Base):
    """Junction table: which marinas a marina_manager can access."""
    __tablename__ = "user_marina_access"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    marina_id = Column(Integer, ForeignKey("marinas.id", ondelete="CASCADE"), primary_key=True)
    granted_at = Column(DateTime, nullable=False, default=utcnow)
    granted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    user = relationship("User", back_populates="marina_access", foreign_keys=[user_id])


class UserBackupCode(Base):
    """One-time recovery codes: shown ONCE, stored as bcrypt (spec §7.1)."""
    __tablename__ = "user_backup_codes"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
                     index=True)
    code_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    used_at = Column(DateTime, nullable=True)


class SetupToken(Base):
    """One-time, time-limited link to set a password (first admin, new users, D20.3).

    Only the sha256 of the token is stored; the token itself exists in the link.
    """
    __tablename__ = "setup_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_setup_tokens_hash"),
        CheckConstraint("expires_at > created_at", name="ck_setup_tokens_expiry"),
    )

    id = Column(Integer, primary_key=True)
    token_hash = Column(String(64), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
                     index=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class AuthAudit(Base):
    """Every login, failure, lockout, 2FA change and user change (spec §4.9).

    Append only. `email_tried` is what was typed — for an unknown e-mail there is
    no user. `detail` is the real reason the response never tells (O14).
    Retention 2 years (§4.7).
    """
    __tablename__ = "auth_audit"
    __table_args__ = (
        Index("ix_auth_audit_created_at", "created_at"),
        Index("ix_auth_audit_user_id", "user_id"),
    )

    id = Column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    email_tried = Column(String(320), nullable=True)
    event = Column(String(40), nullable=False)
    detail = Column(Text, nullable=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source_ip = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
