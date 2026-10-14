"""D21: security agent — its only write, its sources, and its own database role (spec §13.1).

Revision ID: 011
Revises: 010
Create Date: 2026-10-14

Tables: security_alarms, service_windows, decoy_hits, admin_imports,
security_rule_settings.

PostgreSQL only — the role `erp_agent`:
  - created here if it does not exist (needs CREATEROLE). On a server where an
    administrator created it beforehand, nothing is created, only checked;
  - its attributes are CHECKED, never altered: a role that is superuser,
    can create roles or databases, or bypasses RLS is refused — that is a
    decision for a human, not something to fix silently;
  - grants: SELECT on the sources (some by column), INSERT on security_alarms,
    USAGE on its sequence. Nothing else. Everything is first revoked in this
    database, so the result is exact even on a role that held more.

The lists are written out here, literally: a migration is history and must not
change when app/agent/sources.py changes. TC-ERP-AGT-01 compares the live
grants with app/agent/sources.py — if the two ever differ, it fails.

SQLite has no roles; there the tables are all this migration does.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

ROLE = "erp_agent"
SELECT_TABLES = (
    "command_audit", "auth_audit", "audit_log", "sync_log", "reconciliation_runs",
    "session_log", "alarm_log", "pedestal_cache", "outlets", "berths", "service_windows",
    "decoy_hits", "security_alarms", "admin_imports", "security_rule_settings",
)
SELECT_COLUMNS = {
    "cabinets": ("id", "marina_id", "pedestal_pk", "display_id", "device_type", "dock",
                 "smart_mode", "last_heartbeat_at", "last_polled_at", "created_at"),
    "marinas": ("id", "name", "timezone"),
}
INSERT_TABLES = ("security_alarms",)
SEQUENCES = ("security_alarms_id_seq",)


def _json():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _bigid():
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade():
    op.create_table(
        "security_alarms",
        sa.Column("id", _bigid(), nullable=False),
        sa.Column("rule_id", sa.String(60), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("why", sa.Text(), nullable=False),
        sa.Column("evidence", _json(), nullable=False),
        sa.Column("window_from", sa.DateTime(), nullable=True),
        sa.Column("window_to", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("state", sa.String(15), server_default="open", nullable=False),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.CheckConstraint("severity IN ('info', 'warning', 'critical')",
                           name="ck_security_alarms_severity"),
        sa.CheckConstraint("state IN ('open', 'acknowledged', 'closed')",
                           name="ck_security_alarms_state"),
        sa.CheckConstraint("(state = 'open') = (decided_by IS NULL AND decided_at IS NULL)",
                           name="ck_security_alarms_decision"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint", name="uq_security_alarms_fingerprint"),
    )
    op.create_index("ix_security_alarms_created_at", "security_alarms", ["created_at"])

    op.create_table(
        "service_windows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cabinet_id", sa.Integer(), nullable=False),
        sa.Column("from_at", sa.DateTime(), nullable=False),
        sa.Column("to_at", sa.DateTime(), nullable=False),
        sa.Column("announced_by", sa.String(320), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("to_at > from_at", name="ck_service_windows_order"),
        sa.CheckConstraint("length(trim(announced_by)) > 0",
                           name="ck_service_windows_announced_by"),
        sa.ForeignKeyConstraint(["cabinet_id"], ["cabinets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_windows_cabinet_from", "service_windows",
                    ["cabinet_id", "from_at"])

    op.create_table(
        "decoy_hits",
        sa.Column("id", _bigid(), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("decoy", sa.String(200), nullable=False),
        sa.Column("method", sa.String(10), nullable=True),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("source_ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("kind IN ('endpoint', 'account', 'api_key')",
                           name="ck_decoy_hits_kind"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decoy_hits_observed_at", "decoy_hits", ["observed_at"])

    op.create_table(
        "admin_imports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("content", _json(), nullable=False),
        sa.Column("imported_by", sa.Integer(), nullable=True),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["imported_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sha256", name="uq_admin_imports_sha256"),
    )

    op.create_table(
        "security_rule_settings",
        sa.Column("rule_id", sa.String(60), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("mode IN ('shadow', 'active')", name="ck_security_rule_settings_mode"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("rule_id"),
    )

    if op.get_bind().dialect.name == "postgresql":
        _agent_role()


def _agent_role():
    bind = op.get_bind()
    row = bind.execute(sa.text(
        "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls, rolcanlogin "
        "FROM pg_roles WHERE rolname = :r"), {"r": ROLE}).first()
    if row is None:
        # LOGIN without a password: on the VPS it connects by peer auth over the
        # Unix socket as system user erp-agent (pg_hba), never by password.
        bind.execute(sa.text(
            f"CREATE ROLE {ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOREPLICATION NOBYPASSRLS NOINHERIT"))
    else:
        su, cr, cd, rep, rls, _login = row
        if su or cr or cd or rep or rls:
            raise RuntimeError(
                f"role {ROLE} exists with more power than D21 allows (superuser={su}, "
                f"createrole={cr}, createdb={cd}, replication={rep}, bypassrls={rls}) — "
                "fix it by hand first (spec §13.1)")

    for stmt in (
        f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ROLE}",
        f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {ROLE}",
        f"REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM {ROLE}",
        f"GRANT USAGE ON SCHEMA public TO {ROLE}",
    ):
        bind.execute(sa.text(stmt))
    for t in SELECT_TABLES:
        bind.execute(sa.text(f"GRANT SELECT ON {t} TO {ROLE}"))
    for t, cols in SELECT_COLUMNS.items():
        bind.execute(sa.text(f"GRANT SELECT ({', '.join(cols)}) ON {t} TO {ROLE}"))
    for t in INSERT_TABLES:
        bind.execute(sa.text(f"GRANT INSERT ON {t} TO {ROLE}"))
    for s in SEQUENCES:
        bind.execute(sa.text(f"GRANT USAGE ON SEQUENCE {s} TO {ROLE}"))


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        exists = bind.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"),
                              {"r": ROLE}).first()
        if exists:
            for stmt in (
                f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ROLE}",
                f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {ROLE}",
                f"REVOKE ALL ON SCHEMA public FROM {ROLE}",
            ):
                bind.execute(sa.text(stmt))
            # the role is cluster-wide: dropped only if no other database still uses it
            bind.execute(sa.text(
                f"DO $$ BEGIN DROP ROLE {ROLE}; "
                "EXCEPTION WHEN dependent_objects_still_exist OR insufficient_privilege "
                "THEN NULL; END $$"))
    op.drop_table("security_rule_settings")
    op.drop_table("admin_imports")
    op.drop_index("ix_decoy_hits_observed_at", table_name="decoy_hits")
    op.drop_table("decoy_hits")
    op.drop_index("ix_service_windows_cabinet_from", table_name="service_windows")
    op.drop_table("service_windows")
    op.drop_index("ix_security_alarms_created_at", table_name="security_alarms")
    op.drop_table("security_alarms")
