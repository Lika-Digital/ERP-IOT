"""Add last_readings JSON to pedestal_cache for power/water/moisture tracking.

Revision ID: 004
Revises: 003
Create Date: 2026-04-08

Changes:
  - Add last_readings (JSON, nullable) to pedestal_cache
    Stores {event_type: {value, unit, at, ...}} for latest sensor readings.
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("pedestal_cache") as batch_op:
        batch_op.add_column(sa.Column("last_readings", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("pedestal_cache") as batch_op:
        batch_op.drop_column("last_readings")
