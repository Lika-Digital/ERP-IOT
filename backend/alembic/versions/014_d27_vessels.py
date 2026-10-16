"""D27 phase 1: the berth's main vessel (spec §6.10, §10.12 step 4).

Revision ID: 014
Revises: 013
Create Date: 2026-10-16

- vessels: name, registration, owner — the owner is personal data (D15): only in
  the berth's detail, every read of it audited, never on the map or dashboard;
- berth_vessels: which vessel is a berth's main vessel, from when to when; at most
  ONE current (valid_to NULL) per berth, in the database.

No photo here: the reference photo goes to the cabinet and its record waits for
your decision on P1/P2 (§6.12). No match mode or ERP results: D30 phase 2.
"""
from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "vessels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("marina_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("registration", sa.String(60), nullable=True),
        sa.Column("owner_name", sa.String(200), nullable=True),
        sa.Column("owner_contact", sa.String(320), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(320), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.String(320), nullable=True),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_vessels_name"),
        sa.CheckConstraint("length(trim(created_by)) > 0", name="ck_vessels_created_by"),
        sa.ForeignKeyConstraint(["marina_id"], ["marinas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vessels_marina_id", "vessels", ["marina_id"])
    op.create_table(
        "berth_vessels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("berth_id", sa.Integer(), nullable=False),
        sa.Column("vessel_id", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.DateTime(), nullable=False),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("assigned_by", sa.String(320), nullable=False),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_berth_vessels_order"),
        sa.CheckConstraint("length(trim(assigned_by)) > 0", name="ck_berth_vessels_assigned_by"),
        sa.ForeignKeyConstraint(["berth_id"], ["berths.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vessel_id"], ["vessels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_berth_vessels_current", "berth_vessels", ["berth_id"], unique=True,
                    postgresql_where=sa.text("valid_to IS NULL"),
                    sqlite_where=sa.text("valid_to IS NULL"))


def downgrade():
    op.drop_index("uq_berth_vessels_current", table_name="berth_vessels")
    op.drop_table("berth_vessels")
    op.drop_index("ix_vessels_marina_id", table_name="vessels")
    op.drop_table("vessels")
