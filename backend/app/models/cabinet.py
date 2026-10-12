"""Cabinets, their capabilities and outlets (spec §4.1, D3).

Times are naive UTC like every other column in this schema (app/utils/time.py,
spec §11 O18); the spec's TIMESTAMPTZ is a later, all-tables migration.
"""
from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)

from ..database import Base
from ..utils.time import utcnow

OUTLET_NAMES = ("Q1", "Q2", "Q3", "Q4", "V1", "V2")
CAPABILITIES = ("power", "water", "vessel_detect", "camera", "door", "breaker", "load_meter")


class Cabinet(Base):
    __tablename__ = "cabinets"
    __table_args__ = (
        UniqueConstraint("marina_id", "display_id", name="uq_cabinets_marina_display"),
        UniqueConstraint("marina_id", "pedestal_pk", name="uq_cabinets_marina_pk"),
        CheckConstraint("device_type IN ('full', 'retrofit')", name="ck_cabinets_device_type"),
    )

    id = Column(Integer, primary_key=True)
    marina_id = Column(Integer, ForeignKey("marinas.id", ondelete="CASCADE"), nullable=False)
    pedestal_pk = Column(Integer, nullable=False)      # numeric PK ON THE CABINET (load/breaker)
    display_id = Column(String(100), nullable=False)   # 'MAR_KRK_ORM_01'
    device_type = Column(String(20), nullable=False)   # what the cabinet cannot tell us (§0.7 #3)
    base_url = Column(String(500), nullable=False)
    service_email = Column(String(320), nullable=False)
    service_pw_enc = Column(Text, nullable=False)      # Fernet
    erp_api_key_enc = Column(Text, nullable=True)      # channel B; rotation is O9
    dock = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class CabinetCapability(Base):
    __tablename__ = "cabinet_capabilities"
    __table_args__ = (
        CheckConstraint(
            "capability IN ('power', 'water', 'vessel_detect', 'camera', 'door', 'breaker', "
            "'load_meter')", name="ck_capability_name"),
    )

    cabinet_id = Column(Integer, ForeignKey("cabinets.id", ondelete="CASCADE"), primary_key=True)
    capability = Column(String(30), primary_key=True)
    available = Column(Boolean, nullable=False)
    checked_at = Column(DateTime, nullable=False, default=utcnow)


class Outlet(Base):
    """An outlet, always by its real name — never a bare digit (D3, §4.1)."""
    __tablename__ = "outlets"
    __table_args__ = (
        UniqueConstraint("cabinet_id", "outlet_name", name="uq_outlets_cabinet_name"),
        # target of the composite FK from berth_outlets, which copies `medium`
        # so the database itself can enforce the electricity-only uniqueness
        UniqueConstraint("id", "medium", name="uq_outlets_id_medium"),
        CheckConstraint("outlet_name IN ('Q1', 'Q2', 'Q3', 'Q4', 'V1', 'V2')",
                        name="ck_outlets_name"),
        CheckConstraint(
            "(substr(outlet_name, 1, 1) = 'Q' AND medium = 'electricity') OR "
            "(substr(outlet_name, 1, 1) = 'V' AND medium = 'water')",
            name="ck_outlets_medium_matches_name"),
        CheckConstraint("phases IS NULL OR phases IN (1, 3)", name="ck_outlets_phases"),
        CheckConstraint("medium = 'electricity' OR (phases IS NULL AND rated_amps IS NULL)",
                        name="ck_outlets_water_has_no_phases"),
    )

    id = Column(Integer, primary_key=True)
    cabinet_id = Column(Integer, ForeignKey("cabinets.id", ondelete="CASCADE"), nullable=False)
    outlet_name = Column(String(2), nullable=False)
    medium = Column(String(20), nullable=False)        # 'electricity' | 'water'
    phases = Column(Integer, nullable=True)            # 3 for Q1 on a full cabinet
    rated_amps = Column(Integer, nullable=True)
    rated_lpm = Column(Integer, nullable=True)
