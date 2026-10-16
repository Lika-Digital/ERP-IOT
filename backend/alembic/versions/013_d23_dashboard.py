"""D23: main dashboard — the marina's map file, and the security agent's passes (spec §6.6).

Revision ID: 013
Revises: 012
Create Date: 2026-10-16

- marinas.map_svg: the file name of the marina's drawn map under /maps/ (§6.1);
  NULL = no map, the berth list is the whole screen. A file NAME, never a path
  or a URL — a CHECK refuses '/', '\\' and anything not ending in .svg;
- security_agent_passes: one row per agent pass. The Safety & Security card is
  `stale` when the newest row is older than 2x the agent's interval: zero alarms
  from an agent that does not run is not zero (§6.6). The agent may INSERT here
  and nothing else new (app/agent/sources.py, TC-ERP-AGT-01 compares); the
  backend deletes rows older than 7 days (retention.py).

Written by hand from the models; `alembic check` in the boot check proves they agree.
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None

ROLE = "erp_agent"
# what this migration adds to 011's grants (TC-ERP-AGT-01 merges the three)
ADDED_INSERT_TABLES = ("security_agent_passes",)
ADDED_SEQUENCES = ("security_agent_passes_id_seq",)
MAP_SVG_IS_A_FILE_NAME = (
    "map_svg IS NULL OR (map_svg LIKE '%.svg' AND map_svg NOT LIKE '%/%' "
    "AND map_svg NOT LIKE '%\\%' ESCAPE '!' AND map_svg NOT LIKE '.%')")


def upgrade():
    with op.batch_alter_table("marinas") as b:
        b.add_column(sa.Column("map_svg", sa.String(100), nullable=True))
        b.create_check_constraint("ck_marinas_map_svg_file", MAP_SVG_IS_A_FILE_NAME)

    op.create_table(
        "security_agent_passes",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=False),
        sa.Column("rules", sa.Integer(), nullable=False),
        sa.Column("opened", sa.Integer(), nullable=False),
        sa.CheckConstraint("rules >= 0 AND opened >= 0", name="ck_security_agent_passes_counts"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_agent_passes_finished_at", "security_agent_passes",
                    ["finished_at"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and bind.execute(
            sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}).first():
        for t in ADDED_INSERT_TABLES:
            op.execute(f"GRANT INSERT ON {t} TO {ROLE}")
        for s in ADDED_SEQUENCES:
            op.execute(f"GRANT USAGE ON SEQUENCE {s} TO {ROLE}")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and bind.execute(
            sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}).first():
        for s in ADDED_SEQUENCES:
            op.execute(f"REVOKE USAGE ON SEQUENCE {s} FROM {ROLE}")
        for t in ADDED_INSERT_TABLES:
            op.execute(f"REVOKE INSERT ON {t} FROM {ROLE}")
    op.drop_index("ix_security_agent_passes_finished_at", table_name="security_agent_passes")
    op.drop_table("security_agent_passes")
    with op.batch_alter_table("marinas") as b:
        b.drop_constraint("ck_marinas_map_svg_file", type_="check")
        b.drop_column("map_svg")
