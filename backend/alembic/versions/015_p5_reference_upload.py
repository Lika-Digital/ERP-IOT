"""P5: the reference photo goes to the cabinet, per cabinet, under the P1 record (spec §6.12).

Revision ID: 015
Revises: 014
Create Date: 2026-10-16

- cabinet_capabilities: a new capability 'reference_upload' — the ERP Admin's record that
  the cabinet's gateway allows berths.push_image_ext (P1): who, why, and a note when the
  cabinet's 403/503 switched it off. A real cabinet cannot get the record until it ships
  R26 (the server refuses it); until then the upload is tried on the simulator only.
- vessel_photos (P2): what was sent, never the picture — sha256 of the bytes that went
  to the cabinet, size, type, reason, who, when, the Admin's "no recognisable people"
  confirmation (§6.10) and the cabinet's answer. No path, no bytes.
"""
from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None

OLD = ("capability IN ('power', 'water', 'vessel_detect', 'camera', 'door', 'breaker', "
       "'load_meter')")
NEW = ("capability IN ('power', 'water', 'vessel_detect', 'camera', 'door', 'breaker', "
       "'load_meter', 'reference_upload')")
WHO = ("capability <> 'reference_upload' OR "
       "(set_by IS NOT NULL AND reason IS NOT NULL AND length(trim(reason)) >= 3)")


def upgrade():
    with op.batch_alter_table("cabinet_capabilities") as b:
        b.add_column(sa.Column("set_by", sa.String(320), nullable=True))
        b.add_column(sa.Column("reason", sa.Text(), nullable=True))
        b.add_column(sa.Column("note", sa.Text(), nullable=True))
        b.drop_constraint("ck_capability_name", type_="check")
        b.create_check_constraint("ck_capability_name", NEW)
        b.create_check_constraint("ck_capability_reference_upload_who", WHO)

    op.create_table(
        "vessel_photos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vessel_id", sa.Integer(), nullable=False),
        sa.Column("berth_id", sa.Integer(), nullable=False),
        sa.Column("cabinet_id", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("no_people_confirmed", sa.Boolean(), nullable=False),
        sa.Column("uploaded_by", sa.String(320), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=True),
        sa.Column("cabinet_status", sa.Integer(), nullable=True),
        sa.Column("cabinet_detail", sa.Text(), nullable=True),
        sa.CheckConstraint("length(sha256) = 64", name="ck_vessel_photos_sha256"),
        sa.CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name="ck_vessel_photos_size"),
        sa.CheckConstraint("content_type = 'image/jpeg'", name="ck_vessel_photos_type"),
        sa.CheckConstraint("length(trim(reason)) >= 3", name="ck_vessel_photos_reason"),
        sa.CheckConstraint("no_people_confirmed", name="ck_vessel_photos_no_people"),
        sa.ForeignKeyConstraint(["vessel_id"], ["vessels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["berth_id"], ["berths.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cabinet_id"], ["cabinets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vessel_photos_berth_id", "vessel_photos", ["berth_id"])


def downgrade():
    op.drop_index("ix_vessel_photos_berth_id", table_name="vessel_photos")
    op.drop_table("vessel_photos")
    op.execute("DELETE FROM cabinet_capabilities WHERE capability = 'reference_upload'")
    with op.batch_alter_table("cabinet_capabilities") as b:
        b.drop_constraint("ck_capability_reference_upload_who", type_="check")
        b.drop_constraint("ck_capability_name", type_="check")
        b.create_check_constraint("ck_capability_name", OLD)
        b.drop_column("note")
        b.drop_column("reason")
        b.drop_column("set_by")
