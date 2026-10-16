"""Marina model — one record per physical marina installation."""
from sqlalchemy import CheckConstraint, Column, Integer, String, DateTime
from ..database import Base
from ..utils.time import utcnow


class Marina(Base):
    __tablename__ = "marinas"
    __table_args__ = (
        # literally migration 013's text: a file NAME, never a path or a URL
        CheckConstraint("map_svg IS NULL OR (map_svg LIKE '%.svg' AND map_svg NOT LIKE '%/%' "
                        "AND map_svg NOT LIKE '%\\%' ESCAPE '!' AND map_svg NOT LIKE '.%')",
                        name="ck_marinas_map_svg_file"),
    )

    id = Column(Integer, primary_key=True)  # the PK is already indexed (spec §11 O17)
    name = Column(String(200), nullable=False)
    location = Column(String(500), nullable=True)
    timezone = Column(String(100), nullable=False, default="UTC")
    logo_url = Column(String(500), nullable=True)

    # Pedestal SW API connection details
    pedestal_api_base_url = Column(String(500), nullable=False)

    # Service account credentials (replaces pedestal_api_key)
    # Password is encrypted at rest using Fernet (see app/utils/encryption.py).
    # These are nullable at the DB level for migration safety; code enforces non-null.
    pedestal_service_email = Column(String(320), nullable=True)
    pedestal_service_password_encrypted = Column(String(1000), nullable=True)

    # Webhook security
    webhook_secret = Column(String(500), nullable=True)

    # D23 (§6.1, §6.6): file NAME of the drawn map under /maps/; NULL = no map, the
    # berth list is the whole screen
    map_svg = Column(String(100), nullable=True)

    # Status: active | inactive | maintenance
    status = Column(String(50), nullable=False, default="active")

    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
