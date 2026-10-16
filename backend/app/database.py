"""PostgreSQL database session and base model setup."""
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker, DeclarativeBase

from .config import settings
from .utils.time import refuse_aware_datetimes

# Every session in the process, the app's and the tests' alike (spec §4.0).
if not event.contains(Session, "before_flush", refuse_aware_datetimes):
    event.listen(Session, "before_flush", refuse_aware_datetimes)

log = logging.getLogger(__name__)

# For tests the DATABASE_URL is overridden to sqlite:// via env var before import
_connect_args = {}
if settings.database_url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class SchemaNotAtHead(RuntimeError):
    """The database is not at the migrations' head; the app must not start on it (P3)."""


def check_schema_at_head(bind=None) -> None:
    """Spec §8.4 P3: on PostgreSQL only the migrations change the schema. A database
    at another revision would serve half a schema, so the start is refused."""
    from pathlib import Path

    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    heads = set(ScriptDirectory.from_config(cfg).get_heads())
    with (bind or engine).connect() as conn:
        current = set(MigrationContext.configure(conn).get_current_heads())
    if current != heads:
        have = ", ".join(sorted(current)) or "none (empty database)"
        raise SchemaNotAtHead(f"Database is at revision {have}, the code needs "
                              f"{', '.join(sorted(heads))} — run `alembic upgrade head`")


def init_db(bind=None):
    """SQLite (tests, demo): create the tables. PostgreSQL: never create_all — refuse
    to start unless the database is at head (spec §8.4 P3). Nothing is seeded (D20.3)."""
    from . import models  # noqa: F401  — registers every model

    bind = bind or engine
    if bind.dialect.name == "sqlite":
        Base.metadata.create_all(bind=bind)
        log.info("Database tables created/verified (SQLite).")
    else:
        check_schema_at_head(bind)
        log.info("Database is at the migrations' head.")
    # No seeded user (D20.3): the first admin comes from `python -m app.setup_admin`.
