"""Marina service account credentials — replace api_key with JWT service account.

Revision ID: 002
Revises: 001
Create Date: 2026-04-07

Changes:
  - Add pedestal_service_email (String, nullable for migration safety)
  - Add pedestal_service_password_encrypted (String, nullable for migration safety)
  - pedestal_api_base_url already exists — no change
  - Drop pedestal_api_key

NOTE: After running this migration, populate pedestal_service_email and
pedestal_service_password_encrypted for all existing marinas before making
those columns NOT NULL in a subsequent migration.
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add service account email — nullable initially so existing rows don't break
    op.add_column(
        "marinas",
        sa.Column("pedestal_service_email", sa.String(320), nullable=True),
    )

    # Add encrypted service account password — nullable initially
    op.add_column(
        "marinas",
        sa.Column("pedestal_service_password_encrypted", sa.String(1000), nullable=True),
    )

    # Drop the old plain API key column
    op.drop_column("marinas", "pedestal_api_key")


def downgrade() -> None:
    # Restore the api_key column (data will be lost — restore from backup if needed)
    op.add_column(
        "marinas",
        sa.Column("pedestal_api_key", sa.String(500), nullable=True),
    )

    # Remove the new service account columns
    op.drop_column("marinas", "pedestal_service_password_encrypted")
    op.drop_column("marinas", "pedestal_service_email")
