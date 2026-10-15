"""D28: demo marina — real / simulated, cabinets per server, reservations (spec §6.11).

Revision ID: 012
Revises: 011
Create Date: 2026-10-15

- cabinets.is_simulated, and a CHECK that ties it to the simulator's loopback
  address: a real cabinet can never point at the simulator, a simulated one
  never at a real address;
- the cabinet PK is unique per cabinet SERVER (marina, base_url, pk), not per
  marina: two real cabinets in one marina are each pedestal 1 on their own server;
- berths.length_m; berth_reservations (the reservation signal of D2, §3.1);
- customers.is_demo; triggers: billing_records refuses a demo customer or a
  session from a simulated cabinet, credit_ledger refuses a demo customer —
  the same DDL as app/models/billing.py;
- security_alarms.simulated; the agent may read cabinets.is_simulated and
  base_url (app/agent/sources.py, TC-ERP-AGT-01 compares).

Written by hand from the models; `alembic check` in the boot check proves they agree.
"""
from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None

ROLE = "erp_agent"
# what this migration adds to 011's column grants (TC-ERP-AGT-01 merges the two)
ADDED_SELECT_COLUMNS = {"cabinets": ("is_simulated", "base_url")}
SIMULATOR_URL_LIKE = "http://127.0.0.1:%/c/%"
SIMULATED_MATCHES_URL = (
    f"(is_simulated AND base_url LIKE '{SIMULATOR_URL_LIKE}') OR "
    f"(NOT is_simulated AND base_url NOT LIKE '{SIMULATOR_URL_LIKE}')")

# literally the text of app/models/billing.py — a migration is history
_SIM_BILLING = (
    "EXISTS (SELECT 1 FROM customers WHERE id = NEW.customer_id AND is_demo) OR "
    "EXISTS (SELECT 1 FROM sessions s JOIN cabinets c ON c.id = s.cabinet_id "
    "WHERE s.id = NEW.session_id AND c.is_simulated)")
_SIM_LEDGER = "EXISTS (SELECT 1 FROM customers WHERE id = NEW.customer_id AND is_demo)"
GUARD_PG = [
    f"""CREATE OR REPLACE FUNCTION billing_refuses_simulated() RETURNS trigger AS $$
BEGIN
  IF {_SIM_BILLING} THEN
    RAISE EXCEPTION 'simulated data is never billed (D28): billing_records refused';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql""",
    """CREATE TRIGGER billing_records_no_simulated BEFORE INSERT OR UPDATE ON billing_records
FOR EACH ROW EXECUTE FUNCTION billing_refuses_simulated()""",
    f"""CREATE OR REPLACE FUNCTION ledger_refuses_demo() RETURNS trigger AS $$
BEGIN
  IF {_SIM_LEDGER} THEN
    RAISE EXCEPTION 'a demo customer has no ledger (D28): credit_ledger refused';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql""",
    """CREATE TRIGGER credit_ledger_no_demo BEFORE INSERT ON credit_ledger
FOR EACH ROW EXECUTE FUNCTION ledger_refuses_demo()""",
]
GUARD_SQLITE = [
    f"""CREATE TRIGGER billing_records_no_simulated BEFORE INSERT ON billing_records
WHEN {_SIM_BILLING}
BEGIN SELECT RAISE(ABORT, 'simulated data is never billed (D28): billing_records refused'); END""",
    f"""CREATE TRIGGER billing_records_no_simulated_upd BEFORE UPDATE ON billing_records
WHEN {_SIM_BILLING}
BEGIN SELECT RAISE(ABORT, 'simulated data is never billed (D28): billing_records refused'); END""",
    f"""CREATE TRIGGER credit_ledger_no_demo BEFORE INSERT ON credit_ledger
WHEN {_SIM_LEDGER}
BEGIN SELECT RAISE(ABORT, 'a demo customer has no ledger (D28): credit_ledger refused'); END""",
]


def upgrade():
    with op.batch_alter_table("cabinets") as b:
        b.add_column(sa.Column("is_simulated", sa.Boolean(), server_default=sa.false(),
                               nullable=False))
        b.drop_constraint("uq_cabinets_marina_pk", type_="unique")
        b.create_unique_constraint("uq_cabinets_marina_server_pk",
                                   ["marina_id", "base_url", "pedestal_pk"])
        b.create_check_constraint("ck_cabinets_simulated_url", SIMULATED_MATCHES_URL)

    with op.batch_alter_table("berths") as b:
        b.add_column(sa.Column("length_m", sa.Numeric(5, 1), nullable=True))

    op.create_table(
        "berth_reservations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("berth_id", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("ends_at > starts_at", name="ck_berth_reservations_order"),
        sa.CheckConstraint("length(trim(created_by)) > 0", name="ck_berth_reservations_author"),
        sa.ForeignKeyConstraint(["berth_id"], ["berths.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_berth_reservations_berth_time", "berth_reservations",
                    ["berth_id", "starts_at", "ends_at"])

    with op.batch_alter_table("customers") as b:
        b.add_column(sa.Column("is_demo", sa.Boolean(), server_default=sa.false(),
                               nullable=False))

    with op.batch_alter_table("security_alarms") as b:
        b.add_column(sa.Column("simulated", sa.Boolean(), server_default=sa.false(),
                               nullable=False))

    bind = op.get_bind()
    for stmt in (GUARD_PG if bind.dialect.name == "postgresql" else GUARD_SQLITE):
        op.execute(stmt)
    if bind.dialect.name == "postgresql" and bind.execute(
            sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}).first():
        for t, cols in ADDED_SELECT_COLUMNS.items():
            op.execute(f"GRANT SELECT ({', '.join(cols)}) ON {t} TO {ROLE}")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        if bind.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"),
                        {"r": ROLE}).first():
            for t, cols in ADDED_SELECT_COLUMNS.items():
                op.execute(f"REVOKE SELECT ({', '.join(cols)}) ON {t} FROM {ROLE}")
        op.execute("DROP TRIGGER IF EXISTS credit_ledger_no_demo ON credit_ledger")
        op.execute("DROP TRIGGER IF EXISTS billing_records_no_simulated ON billing_records")
        op.execute("DROP FUNCTION IF EXISTS ledger_refuses_demo()")
        op.execute("DROP FUNCTION IF EXISTS billing_refuses_simulated()")
    else:
        for t in ("credit_ledger_no_demo", "billing_records_no_simulated_upd",
                  "billing_records_no_simulated"):
            op.execute(f"DROP TRIGGER IF EXISTS {t}")
    with op.batch_alter_table("security_alarms") as b:
        b.drop_column("simulated")
    with op.batch_alter_table("customers") as b:
        b.drop_column("is_demo")
    op.drop_index("ix_berth_reservations_berth_time", table_name="berth_reservations")
    op.drop_table("berth_reservations")
    with op.batch_alter_table("berths") as b:
        b.drop_column("length_m")
    with op.batch_alter_table("cabinets") as b:
        b.drop_constraint("ck_cabinets_simulated_url", type_="check")
        b.drop_constraint("uq_cabinets_marina_server_pk", type_="unique")
        b.create_unique_constraint("uq_cabinets_marina_pk", ["marina_id", "pedestal_pk"])
        b.drop_column("is_simulated")
