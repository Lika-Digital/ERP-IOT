"""Add temperature tracking columns to pedestal_cache.

Revision ID: 003
Revises: 002
Create Date: 2026-04-08

Changes:
  - Add last_temperature (Float, nullable) to pedestal_cache
  - Add last_temperature_alarm (Boolean, nullable) to pedestal_cache
  - Add last_temperature_at (DateTime, nullable) to pedestal_cache
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("pedestal_cache") as batch_op:
        batch_op.add_column(sa.Column("last_temperature", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("last_temperature_alarm", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("last_temperature_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("pedestal_cache") as batch_op:
        batch_op.drop_column("last_temperature_at")
        batch_op.drop_column("last_temperature_alarm")
        batch_op.drop_column("last_temperature")
