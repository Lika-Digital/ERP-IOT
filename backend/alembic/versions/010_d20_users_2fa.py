"""D20: two roles, TOTP 2FA, backup codes, setup links, auth audit (spec §4.9, §5.3).

Revision ID: 010
Revises: 009
Create Date: 2026-10-13

- users.role: super_admin -> admin, then CHECK (role IN ('admin', 'marina_manager')).
  The migration refuses to run if any other role is in the table: a role the
  CHECK does not know is a decision, not something to map silently.
- users.password_hash becomes nullable: a user created by an admin has no
  password until the one-time link is used (D20.3).
- Existing users keep their password and have NO 2FA: on the next login they
  see only the enrolment screen (spec §7.1 "bez 2FA nema rada").

Written by hand from the models; `alembic check` in the boot check proves they
agree, the schema probes prove the CHECKs hold.
"""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    other = bind.execute(sa.text(
        "SELECT DISTINCT role FROM users WHERE role NOT IN ('super_admin', 'admin', 'marina_manager')"
    )).scalars().all()
    if other:
        raise RuntimeError(f"users holds roles D20 does not know: {other} — decide by hand first")
    bind.execute(sa.text("UPDATE users SET role = 'admin' WHERE role = 'super_admin'"))

    with op.batch_alter_table("users") as b:
        b.alter_column("password_hash", existing_type=sa.String(500), nullable=True)
        b.add_column(sa.Column("totp_secret_enc", sa.Text(), nullable=True))
        b.add_column(sa.Column("totp_confirmed_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("totp_last_step", sa.BigInteger(), nullable=True))
        b.add_column(sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False))
        b.add_column(sa.Column("locked_until", sa.DateTime(), nullable=True))
        b.create_check_constraint("ck_users_role", "role IN ('admin', 'marina_manager')")
        b.create_check_constraint("ck_users_failed_count", "failed_count >= 0")
        b.create_check_constraint("ck_users_totp_confirmed_has_secret",
                                  "totp_confirmed_at IS NULL OR totp_secret_enc IS NOT NULL")

    op.create_table(
        "user_backup_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_backup_codes_user_id", "user_backup_codes", ["user_id"])

    op.create_table(
        "setup_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.CheckConstraint("expires_at > created_at", name="ck_setup_tokens_expiry"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_setup_tokens_hash"),
    )
    op.create_index("ix_setup_tokens_user_id", "setup_tokens", ["user_id"])

    op.create_table(
        "auth_audit",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("email_tried", sa.String(320), nullable=True),
        sa.Column("event", sa.String(40), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("source_ip", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_audit_created_at", "auth_audit", ["created_at"])
    op.create_index("ix_auth_audit_user_id", "auth_audit", ["user_id"])


def downgrade():
    op.drop_index("ix_auth_audit_user_id", table_name="auth_audit")
    op.drop_index("ix_auth_audit_created_at", table_name="auth_audit")
    op.drop_table("auth_audit")
    op.drop_index("ix_setup_tokens_user_id", table_name="setup_tokens")
    op.drop_table("setup_tokens")
    op.drop_index("ix_user_backup_codes_user_id", table_name="user_backup_codes")
    op.drop_table("user_backup_codes")
    with op.batch_alter_table("users") as b:
        b.drop_constraint("ck_users_totp_confirmed_has_secret", type_="check")
        b.drop_constraint("ck_users_failed_count", type_="check")
        b.drop_constraint("ck_users_role", type_="check")
        for c in ("locked_until", "failed_count", "totp_last_step", "totp_confirmed_at",
                  "totp_secret_enc"):
            b.drop_column(c)
        b.alter_column("password_hash", existing_type=sa.String(500), nullable=False)
    op.get_bind().execute(sa.text("UPDATE users SET role = 'super_admin' WHERE role = 'admin'"))
