"""Marina model — one record per physical marina installation."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, func
from ..database import Base


class Marina(Base):
    __tablename__ = "marinas"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    location = Column(String(500), nullable=True)
    timezone = Column(String(100), nullable=False, default="UTC")
    logo_url = Column(String(500), nullable=True)

    # Pedestal SW API connection details
    pedestal_api_base_url = Column(String(500), nullable=False)
    pedestal_api_key = Column(String(500), nullable=False)

    # Webhook security
    webhook_secret = Column(String(500), nullable=True)

    # Status: active | inactive | maintenance
    status = Column(String(50), nullable=False, default="active")

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
