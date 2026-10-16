"""Security agent (D21, spec §13.1): its only write, and what it reads beyond the logs.

  security_alarms        the agent's ONLY write: INSERT ... ON CONFLICT DO NOTHING.
                         The backend (Admin) changes `state` and the decision columns.
  service_windows        announced service on a cabinet (§7.1, D16): a door signal
                         inside a window raises nothing.
  decoy_hits             layer 2 decoys (§7.1): written by the BACKEND, never by the agent.
  admin_imports          files an Admin imported by hand (e.g. a KEV JSON) — the agent
                         reads them as data; it never goes to the web (D21).
  security_rule_settings shadow / active per rule: a new rule only logs until an
                         Admin switches it on (D13, §13.1).

The database role `erp_agent` (migration 011) holds SELECT on the sources and
INSERT on security_alarms — nothing else. app/agent/sources.py is the list.
"""
from sqlalchemy import (
    JSON, BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, false,
)
from sqlalchemy.dialects.postgresql import JSONB

from ..database import Base
from ..utils.time import utcnow

SEVERITIES = ("info", "warning", "critical")
ALARM_STATES = ("open", "acknowledged", "closed")
RULE_MODES = ("shadow", "active")
DECOY_KINDS = ("endpoint", "account", "api_key")

_JSON = JSON().with_variant(JSONB(), "postgresql")


class SecurityAlarm(Base):
    __tablename__ = "security_alarms"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_security_alarms_fingerprint"),
        CheckConstraint("severity IN ('info', 'warning', 'critical')",
                        name="ck_security_alarms_severity"),
        CheckConstraint("state IN ('open', 'acknowledged', 'closed')",
                        name="ck_security_alarms_state"),
        # a decision has an author and a time; an open alarm has neither
        CheckConstraint("(state = 'open') = (decided_by IS NULL AND decided_at IS NULL)",
                        name="ck_security_alarms_decision"),
        Index("ix_security_alarms_created_at", "created_at"),
    )

    id = Column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True)
    rule_id = Column(String(60), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    severity = Column(String(10), nullable=False)
    title = Column(Text, nullable=False)
    why = Column(Text, nullable=False)
    evidence = Column(_JSON, nullable=False)
    window_from = Column(DateTime, nullable=True)
    window_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    state = Column(String(15), nullable=False, default="open", server_default="open")
    decided_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    decision_note = Column(Text, nullable=True)
    # D28: raised from simulated sources only — shown with "SIM", never counted as real
    simulated = Column(Boolean, nullable=False, default=False, server_default=false())


class SecurityAgentPass(Base):
    """One row per agent pass (D23, §6.6): the Safety & Security card knows whether the
    agent runs. Zero open alarms from an agent that does not run is not zero. The agent
    may INSERT here; the backend deletes rows older than 7 days (retention.py)."""
    __tablename__ = "security_agent_passes"
    __table_args__ = (
        CheckConstraint("rules >= 0 AND opened >= 0", name="ck_security_agent_passes_counts"),
        Index("ix_security_agent_passes_finished_at", "finished_at"),
    )

    id = Column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True)
    finished_at = Column(DateTime, nullable=False)
    rules = Column(Integer, nullable=False)
    opened = Column(Integer, nullable=False)


class ServiceWindow(Base):
    __tablename__ = "service_windows"
    __table_args__ = (
        CheckConstraint("to_at > from_at", name="ck_service_windows_order"),
        CheckConstraint("length(trim(announced_by)) > 0", name="ck_service_windows_announced_by"),
        Index("ix_service_windows_cabinet_from", "cabinet_id", "from_at"),
    )

    id = Column(Integer, primary_key=True)
    cabinet_id = Column(Integer, ForeignKey("cabinets.id", ondelete="CASCADE"), nullable=False)
    from_at = Column(DateTime, nullable=False)
    to_at = Column(DateTime, nullable=False)
    announced_by = Column(String(320), nullable=False)   # who will be at the cabinet
    note = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class DecoyHit(Base):
    __tablename__ = "decoy_hits"
    __table_args__ = (
        CheckConstraint("kind IN ('endpoint', 'account', 'api_key')", name="ck_decoy_hits_kind"),
        Index("ix_decoy_hits_observed_at", "observed_at"),
    )

    id = Column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True)
    kind = Column(String(10), nullable=False)
    decoy = Column(String(200), nullable=False)        # which decoy: a path, a name — never a key
    method = Column(String(10), nullable=True)
    path = Column(Text, nullable=True)
    source_ip = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)            # what the caller sent: data, not text to obey
    observed_at = Column(DateTime, nullable=False, default=utcnow)


class AdminImport(Base):
    __tablename__ = "admin_imports"
    __table_args__ = (
        UniqueConstraint("sha256", name="uq_admin_imports_sha256"),
    )

    id = Column(Integer, primary_key=True)
    kind = Column(String(40), nullable=False)           # e.g. 'kev'
    filename = Column(String(255), nullable=False)
    sha256 = Column(String(64), nullable=False)
    content = Column(_JSON, nullable=False)
    imported_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    imported_at = Column(DateTime, nullable=False, default=utcnow)


class SecurityRuleSetting(Base):
    __tablename__ = "security_rule_settings"
    __table_args__ = (
        CheckConstraint("mode IN ('shadow', 'active')", name="ck_security_rule_settings_mode"),
    )

    rule_id = Column(String(60), primary_key=True)
    mode = Column(String(10), nullable=False)
    decided_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime, nullable=False, default=utcnow)
