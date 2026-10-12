"""Models and migrations agree again (spec §11 O17).

Revision ID: 006
Revises: 005
Create Date: 2026-10-12

`alembic check` after `upgrade head` found 9 indexes in the models that no
migration created:
  - `index=True` on the integer PRIMARY KEY of 7 tables — redundant, the PK is
    already indexed. Removed from the models, not added here.
  - `pedestal_id` on alarm_log and session_log — real, both are filtered by
    pedestal. Added here.

`alembic check` is now part of the boot check, so this cannot drift silently
again.
"""
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_alarm_log_pedestal_id", "alarm_log", ["pedestal_id"])
    op.create_index("ix_session_log_pedestal_id", "session_log", ["pedestal_id"])


def downgrade():
    op.drop_index("ix_session_log_pedestal_id", table_name="session_log")
    op.drop_index("ix_alarm_log_pedestal_id", table_name="alarm_log")
