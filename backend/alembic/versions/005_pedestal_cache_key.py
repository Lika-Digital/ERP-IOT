"""Key the API response cache by a real cache_key column instead of a hash.

Revision ID: 005
Revises: 004
Create Date: 2026-10-11

Changes (spec §4.8):
  - Add cache_key (String(255), nullable) to pedestal_cache
  - UNIQUE (marina_id, cache_key)
  - pedestal_id becomes nullable: API cache rows have no pedestal
  - Delete the hash-keyed rows

Why: rows were keyed by abs(hash(cache_key)) % 10**9 written into pedestal_id.
Python randomises str hashes per process, so every restart invented new ids,
left the old rows as orphans and silently broke the stale fallback. The same
column also held real pedestal ids written by the webhook.

Which rows are deleted: those with neither last_temperature nor last_readings.
Those two are the only columns read from webhook rows (dashboard.py); a row
without them is either a hash-keyed API cache row — unreachable after any
restart — or a webhook row whose only content is last_seen_data, which nothing
reads. Rows with readings keep their real pedestal_id and lose nothing.
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "DELETE FROM pedestal_cache "
        "WHERE last_temperature IS NULL AND last_readings IS NULL"
    )
    with op.batch_alter_table("pedestal_cache") as batch_op:
        batch_op.add_column(sa.Column("cache_key", sa.String(255), nullable=True))
        batch_op.alter_column("pedestal_id", existing_type=sa.Integer(), nullable=True)
        batch_op.create_unique_constraint(
            "uq_pedestal_cache_marina_key", ["marina_id", "cache_key"]
        )


def downgrade():
    op.execute("DELETE FROM pedestal_cache WHERE cache_key IS NOT NULL")
    with op.batch_alter_table("pedestal_cache") as batch_op:
        batch_op.drop_constraint("uq_pedestal_cache_marina_key", type_="unique")
        batch_op.alter_column("pedestal_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("cache_key")
