"""users.email: one uniqueness rule, not two (spec §11 O17, found on PostgreSQL).

Revision ID: 008
Revises: 007
Create Date: 2026-10-12

Migration 001 made users.email unique twice: `unique=True` on the column (a
UNIQUE constraint, `users_email_key` on PostgreSQL) AND a unique index
`ix_users_email`. The model declares only the index. SQLite turns the inline
UNIQUE into an internal autoindex that Alembic ignores, so the drift was
invisible locally; `alembic check` against PostgreSQL in CI found it on the
first phase-3 run.

The unique index stays and still enforces uniqueness; the redundant constraint
goes. Its name is read from the catalogue, not assumed.
"""
from alembic import op
from sqlalchemy import text

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return   # SQLite: the inline UNIQUE is an internal autoindex; nothing to drop
    names = bind.execute(text(
        "SELECT con.conname FROM pg_constraint con "
        "JOIN pg_class rel ON rel.oid = con.conrelid "
        "JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = ANY(con.conkey) "
        "WHERE rel.relname = 'users' AND con.contype = 'u' AND att.attname = 'email'"
    )).scalars().all()
    for name in names:
        op.drop_constraint(name, "users", type_="unique")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.create_unique_constraint("users_email_key", "users", ["email"])
