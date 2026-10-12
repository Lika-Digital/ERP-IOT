"""Phase 4: collection, reconciliation, webhook per cabinet, retention (spec §4.6, §4.7, §5.2, D19).

Revision ID: 009
Revises: 008
Create Date: 2026-10-12

Written by hand from the models (the repo has no autogenerate template); the
boot check's `alembic check` proves this file and the models agree, and the
schema probes prove the CHECKs hold — `alembic check` does not compare CHECKs.

consumption_intervals is RECREATED: phase 3 created it but nothing ever wrote
to it, and it changes shape (an interval now belongs to an outlet; the session
is optional, D19). The migration refuses to run if the table holds rows.
Batch mode is used for the ALTERs so SQLite gets them too.
"""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def _intervals_v4():
    op.create_table(
        "consumption_intervals",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("outlet_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=True),
        sa.Column("standalone", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("from_at", sa.DateTime(), nullable=False),
        sa.Column("to_at", sa.DateTime(), nullable=False),
        sa.Column("energy_kwh", sa.Numeric(12, 4), nullable=True),
        sa.Column("water_liters", sa.Numeric(12, 3), nullable=True),
        sa.Column("meter_from", sa.Numeric(14, 4), nullable=True),
        sa.Column("meter_to", sa.Numeric(14, 4), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.CheckConstraint("NOT (standalone AND session_id IS NOT NULL)",
                           name="ck_intervals_standalone_has_no_session"),
        sa.CheckConstraint("to_at > from_at", name="ck_intervals_forward"),
        sa.CheckConstraint("energy_kwh IS NULL OR energy_kwh >= 0",
                           name="ck_intervals_energy_not_negative"),
        sa.CheckConstraint("water_liters IS NULL OR water_liters >= 0",
                           name="ck_intervals_water_not_negative"),
        sa.CheckConstraint("source IN ('register', 'integrated_legacy', 'unknown')",
                           name="ck_intervals_source"),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consumption_intervals_outlet_to", "consumption_intervals",
                    ["outlet_id", "to_at"])
    op.create_index("ix_consumption_intervals_to_at", "consumption_intervals", ["to_at"])
    op.create_index("ix_consumption_intervals_session_id", "consumption_intervals",
                    ["session_id"])


def _intervals_v3():
    op.create_table(
        "consumption_intervals",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("from_at", sa.DateTime(), nullable=False),
        sa.Column("to_at", sa.DateTime(), nullable=False),
        sa.Column("energy_kwh", sa.Numeric(12, 4), nullable=True),
        sa.Column("water_liters", sa.Numeric(12, 3), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consumption_intervals_session_id", "consumption_intervals",
                    ["session_id"])


def upgrade():
    rows = op.get_bind().execute(sa.text("SELECT count(*) FROM consumption_intervals")).scalar()
    if rows:
        raise RuntimeError(f"consumption_intervals holds {rows} rows; migration 009 recreates "
                           "it and will not drop data — migrate them by hand first")
    op.drop_index("ix_consumption_intervals_session_id", table_name="consumption_intervals")
    op.drop_table("consumption_intervals")
    _intervals_v4()

    op.create_table(
        "consumption_monthly",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("outlet_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("standalone", sa.Boolean(), nullable=False),
        sa.Column("energy_kwh", sa.Numeric(14, 4), nullable=True),
        sa.Column("water_liters", sa.Numeric(14, 3), nullable=True),
        sa.Column("interval_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("outlet_id", "month", "standalone", name="uq_consumption_monthly"),
    )
    op.create_table(
        "outlet_meter_state",
        sa.Column("outlet_id", sa.Integer(), nullable=False),
        sa.Column("energy_kwh", sa.Numeric(14, 4), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=False),
        sa.Column("last_interval_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("outlet_id"),
    )
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("cabinet_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("window_from", sa.DateTime(), nullable=True),
        sa.Column("window_to", sa.DateTime(), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("sessions_seen", sa.Integer(), nullable=False),
        sa.Column("sessions_updated", sa.Integer(), nullable=False),
        sa.Column("sessions_unknown", sa.Integer(), nullable=False),
        sa.Column("sessions_acked", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint("mode IN ('range', 'by_user')", name="ck_reconciliation_mode"),
        sa.ForeignKeyConstraint(["cabinet_id"], ["cabinets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reconciliation_runs_cabinet_id", "reconciliation_runs", ["cabinet_id"])
    op.create_index("ix_reconciliation_runs_started_at", "reconciliation_runs", ["started_at"])

    with op.batch_alter_table("sessions") as b:
        b.add_column(sa.Column("reconciled_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("ack_sent_at", sa.DateTime(), nullable=True))
        b.create_check_constraint("ck_sessions_billed_is_reconciled",
                                  "billing_state <> 'billed' OR reconciled_at IS NOT NULL")

    with op.batch_alter_table("cabinets") as b:
        b.add_column(sa.Column("webhook_key_enc", sa.Text(), nullable=True))
        b.add_column(sa.Column("webhook_hmac", sa.Boolean(), server_default=sa.false(),
                               nullable=False))
        b.add_column(sa.Column("webhook_secret_enc", sa.Text(), nullable=True))
        b.add_column(sa.Column("smart_mode", sa.Boolean(), nullable=True))
        b.add_column(sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("last_polled_at", sa.DateTime(), nullable=True))
        b.create_check_constraint("ck_cabinets_hmac_has_secret",
                                  "NOT webhook_hmac OR webhook_secret_enc IS NOT NULL")

    with op.batch_alter_table("command_audit") as b:
        b.add_column(sa.Column("outcome", sa.String(40), nullable=True))
        b.add_column(sa.Column("completed_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("alarm_log") as b:
        b.add_column(sa.Column("cabinet_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("cabinet_alarm_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("source", sa.String(10), nullable=True))
        b.create_unique_constraint("uq_alarm_log_cabinet_alarm", ["cabinet_id", "cabinet_alarm_id"])
        b.create_foreign_key("fk_alarm_log_cabinet_id", "cabinets", ["cabinet_id"], ["id"],
                             ondelete="CASCADE")


def downgrade():
    with op.batch_alter_table("alarm_log") as b:
        b.drop_constraint("fk_alarm_log_cabinet_id", type_="foreignkey")
        b.drop_constraint("uq_alarm_log_cabinet_alarm", type_="unique")
        b.drop_column("source")
        b.drop_column("cabinet_alarm_id")
        b.drop_column("cabinet_id")
    with op.batch_alter_table("command_audit") as b:
        b.drop_column("completed_at")
        b.drop_column("outcome")
    with op.batch_alter_table("cabinets") as b:
        b.drop_constraint("ck_cabinets_hmac_has_secret", type_="check")
        for c in ("last_polled_at", "last_heartbeat_at", "smart_mode", "webhook_secret_enc",
                  "webhook_hmac", "webhook_key_enc"):
            b.drop_column(c)
    with op.batch_alter_table("sessions") as b:
        b.drop_constraint("ck_sessions_billed_is_reconciled", type_="check")
        b.drop_column("ack_sent_at")
        b.drop_column("reconciled_at")
    op.drop_index("ix_reconciliation_runs_started_at", table_name="reconciliation_runs")
    op.drop_index("ix_reconciliation_runs_cabinet_id", table_name="reconciliation_runs")
    op.drop_table("reconciliation_runs")
    op.drop_table("outlet_meter_state")
    op.drop_table("consumption_monthly")
    op.drop_index("ix_consumption_intervals_session_id", table_name="consumption_intervals")
    op.drop_index("ix_consumption_intervals_to_at", table_name="consumption_intervals")
    op.drop_index("ix_consumption_intervals_outlet_to", table_name="consumption_intervals")
    op.drop_table("consumption_intervals")
    _intervals_v3()
