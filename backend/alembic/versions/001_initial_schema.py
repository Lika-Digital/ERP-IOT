"""Initial schema — all tables for Phase 1.

Revision ID: 001
Revises:
Create Date: 2026-04-05
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── marinas ──────────────────────────────────────────────────────────────
    op.create_table(
        "marinas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("timezone", sa.String(100), nullable=False, server_default="UTC"),
        sa.Column("logo_url", sa.String(500), nullable=True),
        sa.Column("pedestal_api_base_url", sa.String(500), nullable=False),
        sa.Column("pedestal_api_key", sa.String(500), nullable=False),
        sa.Column("webhook_secret", sa.String(500), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(500), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="marina_manager"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── user_marina_access ────────────────────────────────────────────────────
    op.create_table(
        "user_marina_access",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("marina_id", sa.Integer(), sa.ForeignKey("marinas.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("granted_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    # ── pedestal_cache ────────────────────────────────────────────────────────
    op.create_table(
        "pedestal_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("marina_id", sa.Integer(), sa.ForeignKey("marinas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pedestal_id", sa.Integer(), nullable=False),
        sa.Column("last_seen_data", sa.JSON(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_pedestal_cache_marina_id", "pedestal_cache", ["marina_id"])
    op.create_index("ix_pedestal_cache_pedestal_id", "pedestal_cache", ["pedestal_id"])

    # ── alarm_log ─────────────────────────────────────────────────────────────
    op.create_table(
        "alarm_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("marina_id", sa.Integer(), sa.ForeignKey("marinas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pedestal_id", sa.Integer(), nullable=False),
        sa.Column("alarm_data", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("acknowledged_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_alarm_log_marina_id", "alarm_log", ["marina_id"])
    op.create_index("ix_alarm_log_received_at", "alarm_log", ["received_at"])

    # ── session_log ───────────────────────────────────────────────────────────
    op.create_table(
        "session_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("marina_id", sa.Integer(), sa.ForeignKey("marinas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pedestal_id", sa.Integer(), nullable=False),
        sa.Column("session_data", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_session_log_marina_id", "session_log", ["marina_id"])
    op.create_index("ix_session_log_recorded_at", "session_log", ["recorded_at"])

    # ── sync_log ──────────────────────────────────────────────────────────────
    op.create_table(
        "sync_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("marina_id", sa.Integer(), sa.ForeignKey("marinas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sync_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_sync_log_marina_id", "sync_log", ["marina_id"])

    # ── audit_log ─────────────────────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("marina_id", sa.Integer(), sa.ForeignKey("marinas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pedestal_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("performed_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_marina_id", "audit_log", ["marina_id"])
    op.create_index("ix_audit_log_performed_at", "audit_log", ["performed_at"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("sync_log")
    op.drop_table("session_log")
    op.drop_table("alarm_log")
    op.drop_table("pedestal_cache")
    op.drop_table("user_marina_access")
    op.drop_table("users")
    op.drop_table("marinas")
