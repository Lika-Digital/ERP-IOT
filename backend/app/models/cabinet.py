"""Cabinets, their capabilities and outlets (spec §4.1, D3).

Times are naive UTC like every other column in this schema (app/utils/time.py,
spec §11 O18); the spec's TIMESTAMPTZ is a later, all-tables migration.
"""
from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, false,
)

from ..database import Base
from ..utils.time import utcnow

OUTLET_NAMES = ("Q1", "Q2", "Q3", "Q4", "V1", "V2")
SIMULATOR_URL_LIKE = "http://127.0.0.1:%/c/%"
SIMULATED_MATCHES_URL = (
    f"(is_simulated AND base_url LIKE '{SIMULATOR_URL_LIKE}') OR "
    f"(NOT is_simulated AND base_url NOT LIKE '{SIMULATOR_URL_LIKE}')")
CAPABILITIES = ("power", "water", "vessel_detect", "camera", "door", "breaker", "load_meter")


class Cabinet(Base):
    __tablename__ = "cabinets"
    __table_args__ = (
        UniqueConstraint("marina_id", "display_id", name="uq_cabinets_marina_display"),
        # a PK is unique per cabinet SERVER: two real cabinets in one marina (D28,
        # Krk and marina-iot) are each pedestal 1 on their own server
        UniqueConstraint("marina_id", "base_url", "pedestal_pk",
                         name="uq_cabinets_marina_server_pk"),
        # D28: simulated <=> the simulator's loopback address. A real cabinet can never
        # point at the simulator, and a simulated one never at a real address.
        CheckConstraint(SIMULATED_MATCHES_URL, name="ck_cabinets_simulated_url"),
        CheckConstraint("device_type IN ('full', 'retrofit')", name="ck_cabinets_device_type"),
        # HMAC on: there must be a secret to check against (§5.2)
        CheckConstraint("NOT webhook_hmac OR webhook_secret_enc IS NOT NULL",
                        name="ck_cabinets_hmac_has_secret"),
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
    # webhook receiver (§5.2): the X-API-Key THIS cabinet sends, and the HMAC switch.
    # No key stored -> every webhook from it is refused (the cabinet sends an EMPTY
    # key when none is set, NALAZ 6.1).
    webhook_key_enc = Column(Text, nullable=True)
    webhook_hmac = Column(Boolean, nullable=False, default=False, server_default=false())
    webhook_secret_enc = Column(Text, nullable=True)
    # collector state (§5.2): what health said last time
    smart_mode = Column(Boolean, nullable=True)        # NULL = never read
    last_heartbeat_at = Column(DateTime, nullable=True)
    last_polled_at = Column(DateTime, nullable=True)
    # D28: real or simulated, carried to everything that comes from it
    is_simulated = Column(Boolean, nullable=False, default=False, server_default=false())


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
