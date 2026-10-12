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


def init_db():
    """Create all tables and seed default data."""
    from . import models  # noqa: F401  — registers every model

    Base.metadata.create_all(bind=engine)
    log.info("Database tables created/verified.")
    _seed_defaults()


def _seed_defaults():
    """Seed the super_admin user on first run if DEFAULT_ADMIN_PASSWORD is set."""
    if not settings.default_admin_password:
        return

    from .models.user import User
    from passlib.context import CryptContext

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == settings.default_admin_email).first()
        if not existing:
            user = User(
                email=settings.default_admin_email,
                password_hash=pwd_ctx.hash(settings.default_admin_password),
                full_name="Super Admin",
                role="super_admin",
                is_active=True,
            )
            db.add(user)
            db.commit()
            log.info(f"Seeded default super_admin: {settings.default_admin_email}")
    except Exception as exc:
        log.error(f"Failed to seed default admin: {exc}")
        db.rollback()
    finally:
        db.close()
