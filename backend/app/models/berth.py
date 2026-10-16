"""Berths and the berth -> outlet mapping, on both sides (spec §4.2, §4.3, D1, D18)."""
from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer,
    Numeric, String, Text, UniqueConstraint, text, true,
)
from sqlalchemy.dialects.postgresql import JSONB

from ..database import Base
from ..utils.time import utcnow


class Berth(Base):
    """Commercial identity of a berth (D1). The marina sees `berth_number`."""
    __tablename__ = "berths"
    __table_args__ = (
        UniqueConstraint("marina_id", "berth_number", name="uq_berths_marina_number"),
        UniqueConstraint("cabinet_id", "cabinet_berth_id", name="uq_berths_cabinet_berth"),
    )

    id = Column(Integer, primary_key=True)
    marina_id = Column(Integer, ForeignKey("marinas.id", ondelete="CASCADE"), nullable=False)
    berth_number = Column(String(50), nullable=False)
    svg_id = Column(String(100), nullable=True)
    # Which berth ON THE CABINET this is — the vessel signal (state_code from
    # berths.list) is per cabinet berth. Not in spec v5 §4.2; added in phase 3.
    cabinet_id = Column(Integer, ForeignKey("cabinets.id", ondelete="SET NULL"), nullable=True)
    cabinet_berth_id = Column(Integer, nullable=True)
    length_m = Column(Numeric(5, 1), nullable=True)      # D28: 20 / 15 / 10 m pontoons
    created_at = Column(DateTime, nullable=False, default=utcnow)


class BerthReservation(Base):
    """The reservation signal of D2 (§3.1): the ERP's own, never the cabinet's."""
    __tablename__ = "berth_reservations"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_berth_reservations_order"),
        CheckConstraint("length(trim(created_by)) > 0", name="ck_berth_reservations_author"),
        Index("ix_berth_reservations_berth_time", "berth_id", "starts_at", "ends_at"),
    )

    id = Column(Integer, primary_key=True)
    berth_id = Column(Integer, ForeignKey("berths.id", ondelete="CASCADE"), nullable=False)
    starts_at = Column(DateTime, nullable=False)        # naive UTC (§4.0)
    ends_at = Column(DateTime, nullable=False)
    note = Column(Text, nullable=True)                  # no customer name here (D15)
    created_by = Column(String(320), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class BerthOutlet(Base):
    """The ERP's side of the mapping. Who changed it is ALWAYS recorded (D1, D18).

    `medium` is a copy of outlets.medium, held consistent by a composite FK
    (outlet_id, medium) -> outlets(id, medium). That lets two partial unique
    indexes say what D1 says, in the database rather than in code:
      - one electricity outlet serves at most one berth;
      - one berth has at most one electricity outlet;
    and, deliberately, nothing for water: a valve may be shared.
    """
    __tablename__ = "berth_outlets"
    __table_args__ = (
        ForeignKeyConstraint(["outlet_id", "medium"], ["outlets.id", "outlets.medium"],
                             ondelete="CASCADE", name="fk_berth_outlets_outlet_medium"),
        CheckConstraint("source IN ('erp_manual', 'cabinet', 'confirmed')",
                        name="ck_berth_outlets_source"),
        CheckConstraint("length(trim(assigned_by)) > 0", name="ck_berth_outlets_assigned_by"),
        Index("uq_berth_outlets_electric_outlet", "outlet_id", unique=True,
              postgresql_where=text("medium = 'electricity'"),
              sqlite_where=text("medium = 'electricity'")),
        Index("uq_berth_outlets_electric_berth", "berth_id", unique=True,
              postgresql_where=text("medium = 'electricity'"),
              sqlite_where=text("medium = 'electricity'")),
    )

    berth_id = Column(Integer, ForeignKey("berths.id", ondelete="CASCADE"), primary_key=True)
    outlet_id = Column(Integer, primary_key=True)
    medium = Column(String(20), nullable=False)
    source = Column(String(20), nullable=False)
    assigned_by = Column(String(320), nullable=False)   # never a default
    assigned_at = Column(DateTime, nullable=False, default=utcnow)


class BerthOutletCabinet(Base):
    """What the CABINET claims. The ERP never writes here except from a cabinet read (D18)."""
    __tablename__ = "berth_outlets_cabinet"

    cabinet_id = Column(Integer, ForeignKey("cabinets.id", ondelete="CASCADE"), primary_key=True)
    outlet_name = Column(String(2), primary_key=True)
    cabinet_berth_id = Column(Integer, nullable=True)
    assigned_by = Column(String(320), nullable=True)
    assigned_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, nullable=False, default=utcnow)


class MappingComparison(Base):
    """Result of comparing the two sides; a state, not history (§4.3)."""
    __tablename__ = "mapping_comparison"
    __table_args__ = (
        CheckConstraint("state IN ('unverifiable', 'in_sync', 'divergent')",
                        name="ck_mapping_comparison_state"),
    )

    cabinet_id = Column(Integer, ForeignKey("cabinets.id", ondelete="CASCADE"), primary_key=True)
    state = Column(String(20), nullable=False)
    divergent_rows = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    checked_at = Column(DateTime, nullable=False, default=utcnow)


class OutletNfcTag(Base):
    """NFC tag on an outlet, in BOTH byte orders; the ERP is the master (D6.1, D6.2)."""
    __tablename__ = "outlet_nfc_tags"
    __table_args__ = (
        UniqueConstraint("uid_primary", name="uq_nfc_uid_primary"),
        UniqueConstraint("uid_reversed", name="uq_nfc_uid_reversed"),
        # the two UNIQUE constraints are the indexes the lookup uses (§4.4) —
        # a second, plain index on the same column would be O17 again
        CheckConstraint("length(trim(provisioned_by)) > 0", name="ck_nfc_provisioned_by"),
    )

    id = Column(Integer, primary_key=True)
    outlet_id = Column(Integer, ForeignKey("outlets.id", ondelete="CASCADE"), nullable=False)
    uid_primary = Column(String(64), nullable=False)    # '35:B2:5A:04:09:01:04:E0'
    uid_reversed = Column(String(64), nullable=False)   # 'E0:04:01:09:04:5A:B2:35'
    tag_standard = Column(String(20), nullable=False, default="ISO15693",
                          server_default="ISO15693")
    provisioned_by = Column(String(320), nullable=False)
    provisioned_at = Column(DateTime, nullable=False, default=utcnow)
    active = Column(Boolean, nullable=False, default=True, server_default=true())
    note = Column(Text, nullable=True)


class Vessel(Base):
    """A berth's vessel (D27, §6.10). The owner is personal data (D15): shown only in the
    berth's detail, every read audited, never on the map or the dashboard."""
    __tablename__ = "vessels"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_vessels_name"),
        CheckConstraint("length(trim(created_by)) > 0", name="ck_vessels_created_by"),
        Index("ix_vessels_marina_id", "marina_id"),
    )

    id = Column(Integer, primary_key=True)
    marina_id = Column(Integer, ForeignKey("marinas.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(120), nullable=False)
    registration = Column(String(60), nullable=True)
    owner_name = Column(String(200), nullable=True)
    owner_contact = Column(String(320), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    created_by = Column(String(320), nullable=False)
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(String(320), nullable=True)


class BerthVessel(Base):
    """A berth's main vessel over time; at most one current (valid_to NULL) per berth."""
    __tablename__ = "berth_vessels"
    __table_args__ = (
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_berth_vessels_order"),
        CheckConstraint("length(trim(assigned_by)) > 0", name="ck_berth_vessels_assigned_by"),
        Index("uq_berth_vessels_current", "berth_id", unique=True,
              postgresql_where=text("valid_to IS NULL"), sqlite_where=text("valid_to IS NULL")),
    )

    id = Column(Integer, primary_key=True)
    berth_id = Column(Integer, ForeignKey("berths.id", ondelete="CASCADE"), nullable=False)
    vessel_id = Column(Integer, ForeignKey("vessels.id", ondelete="CASCADE"), nullable=False)
    valid_from = Column(DateTime, nullable=False, default=utcnow)
    valid_to = Column(DateTime, nullable=True)
    assigned_by = Column(String(320), nullable=False)
