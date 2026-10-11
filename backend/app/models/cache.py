"""Cache and log models for pedestal data, alarms, sessions, and sync operations."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON, Float, UniqueConstraint
from ..database import Base


class PedestalCache(Base):
    """Last-known data, used for stale-data fallback and webhook readings.

    Two identity spaces, never mixed in one column (spec §4.8):
      - API response cache: `cache_key` set (e.g. "list_pedestals"), pedestal_id NULL
      - webhook rows: real `pedestal_id` from the cabinet, cache_key NULL
    """
    __tablename__ = "pedestal_cache"
    __table_args__ = (
        UniqueConstraint("marina_id", "cache_key", name="uq_pedestal_cache_marina_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    marina_id = Column(Integer, ForeignKey("marinas.id", ondelete="CASCADE"), nullable=False, index=True)
    pedestal_id = Column(Integer, nullable=True, index=True)
    cache_key = Column(String(255), nullable=True)
    last_seen_data = Column(JSON, nullable=True)  # Full API response payload
    last_synced_at = Column(DateTime, nullable=True)
    is_stale = Column(Boolean, nullable=False, default=False)
    # Latest temperature reading from webhook
    last_temperature = Column(Float, nullable=True)
    last_temperature_alarm = Column(Boolean, nullable=True)
    last_temperature_at = Column(DateTime, nullable=True)
    # Latest sensor readings by type: {type: {value, unit, at, ...}}
    last_readings = Column(JSON, nullable=True)


class AlarmLog(Base):
    """Persistent log of all alarm events received via webhook or polled."""
    __tablename__ = "alarm_log"

    id = Column(Integer, primary_key=True, index=True)
    marina_id = Column(Integer, ForeignKey("marinas.id", ondelete="CASCADE"), nullable=False, index=True)
    pedestal_id = Column(Integer, nullable=False, index=True)
    alarm_data = Column(JSON, nullable=False)  # Raw alarm payload from Pedestal SW
    received_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class SessionLog(Base):
    """Log of all session events forwarded from Pedestal SW via webhooks."""
    __tablename__ = "session_log"

    id = Column(Integer, primary_key=True, index=True)
    marina_id = Column(Integer, ForeignKey("marinas.id", ondelete="CASCADE"), nullable=False, index=True)
    pedestal_id = Column(Integer, nullable=False, index=True)
    session_data = Column(JSON, nullable=False)  # Raw session payload
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class SyncLog(Base):
    """Tracks every API call made to each marina's Pedestal SW."""
    __tablename__ = "sync_log"

    id = Column(Integer, primary_key=True, index=True)
    marina_id = Column(Integer, ForeignKey("marinas.id", ondelete="CASCADE"), nullable=False, index=True)
    sync_type = Column(String(100), nullable=False)  # e.g. 'list_pedestals', 'get_health'
    status = Column(String(50), nullable=False)  # 'success' | 'error' | 'stale'
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)


class AuditLog(Base):
    """Audit trail for all control actions (allow/deny/stop) performed by users."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    marina_id = Column(Integer, ForeignKey("marinas.id", ondelete="CASCADE"), nullable=False, index=True)
    pedestal_id = Column(Integer, nullable=True)
    action = Column(String(100), nullable=False)  # e.g. 'allow_session', 'deny_session'
    target_id = Column(Integer, nullable=True)   # e.g. session_id, alarm_id
    details = Column(JSON, nullable=True)         # Extra context
    performed_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
