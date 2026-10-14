"""Customers, contracts, credit, tariffs, billing records (spec §4.5, D9).

The credit ledger is APPEND-ONLY. That is enforced by the database, not by
discipline: a trigger refuses UPDATE and DELETE on both PostgreSQL and SQLite,
created from the same DDL by the migration and by create_all (tests).
"""
from sqlalchemy import (
    DDL, BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint, event, false, text,
)

from ..database import Base
from ..utils.time import utcnow


class Customer(Base):
    """A customer of the marina — NOT an operator (users). Name never shown on marina screens (D15)."""
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("marina_id", "external_ref", name="uq_customers_marina_ref"),
    )

    id = Column(Integer, primary_key=True)
    marina_id = Column(Integer, ForeignKey("marinas.id"), nullable=False)
    external_ref = Column(String(100), nullable=True)   # id from the mobile app
    full_name = Column(String(200), nullable=False)
    email = Column(String(320), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Contract(Base):
    __tablename__ = "contracts"
    __table_args__ = (
        CheckConstraint("billing_mode IN ('prepaid', 'postpaid')", name="ck_contracts_mode"),
    )

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    # A forgotten setting must never mean unlimited consumption (D9): default prepaid,
    # in the DATABASE, so a row inserted by anything at all gets it.
    billing_mode = Column(String(10), nullable=False, default="prepaid",
                          server_default="prepaid")
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)
    blocked = Column(Boolean, nullable=False, default=False, server_default=false())
    max_unpaid = Column(Numeric(10, 2), nullable=True)
    max_kwh_session = Column(Numeric(10, 3), nullable=True)
    max_session_min = Column(Integer, nullable=True)
    tariff_id = Column(Integer, ForeignKey("tariffs.id"), nullable=True)  # NULL = marina tariff


class CreditLedger(Base):
    """Append-only. Balance = balance_after of the newest row (§4.5)."""
    __tablename__ = "credit_ledger"
    __table_args__ = (
        CheckConstraint("reason IN ('topup', 'consumption', 'adjustment', 'refund')",
                        name="ck_credit_reason"),
        CheckConstraint("length(trim(created_by)) > 0", name="ck_credit_created_by"),
        CheckConstraint("reason <> 'consumption' OR session_id IS NOT NULL",
                        name="ck_credit_consumption_has_session"),
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    delta = Column(Numeric(10, 2), nullable=False)
    reason = Column(String(20), nullable=False)
    session_id = Column(BigInteger, nullable=True)
    balance_after = Column(Numeric(10, 2), nullable=False)
    created_by = Column(String(320), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)


# The same DDL is used by migration 007; keep them identical.
CREDIT_LEDGER_GUARD_PG = [
    """CREATE OR REPLACE FUNCTION credit_ledger_append_only() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'credit_ledger is append-only (spec 4.5): % refused', TG_OP;
END;
$$ LANGUAGE plpgsql""",
    """CREATE TRIGGER credit_ledger_no_update BEFORE UPDATE OR DELETE ON credit_ledger
FOR EACH ROW EXECUTE FUNCTION credit_ledger_append_only()""",
]
CREDIT_LEDGER_GUARD_SQLITE = [
    """CREATE TRIGGER credit_ledger_no_update BEFORE UPDATE ON credit_ledger
BEGIN SELECT RAISE(ABORT, 'credit_ledger is append-only (spec 4.5): UPDATE refused'); END""",
    """CREATE TRIGGER credit_ledger_no_delete BEFORE DELETE ON credit_ledger
BEGIN SELECT RAISE(ABORT, 'credit_ledger is append-only (spec 4.5): DELETE refused'); END""",
]
# DDL() formats its text with %, so plpgsql's own `%` is escaped here; the
# migration runs the same text through op.execute, which does not format.
for _stmt in CREDIT_LEDGER_GUARD_PG:
    event.listen(CreditLedger.__table__, "after_create",
                 DDL(_stmt.replace("%", "%%")).execute_if(dialect="postgresql"))
for _stmt in CREDIT_LEDGER_GUARD_SQLITE:
    event.listen(CreditLedger.__table__, "after_create",
                 DDL(_stmt.replace("%", "%%")).execute_if(dialect="sqlite"))


class Tariff(Base):
    """Model (c), pilot uses one price per medium (§4.5). Water is priced per LITRE."""
    __tablename__ = "tariffs"
    __table_args__ = (
        UniqueConstraint("marina_id", "medium", "time_band", "valid_from",
                         name="uq_tariffs_band"),
        CheckConstraint("medium IN ('electricity', 'water')", name="ck_tariffs_medium"),
    )

    id = Column(Integer, primary_key=True)
    marina_id = Column(Integer, ForeignKey("marinas.id", ondelete="CASCADE"), nullable=False)
    medium = Column(String(20), nullable=False)
    unit_price = Column(Numeric(10, 4), nullable=False)   # EUR/kWh | EUR/litre
    currency = Column(String(3), nullable=False, default="EUR", server_default="EUR")
    vat_rate = Column(Numeric(5, 2), nullable=False)
    time_band = Column(String(10), nullable=True)
    band_from = Column(String(5), nullable=True)          # 'HH:MM'; NULL in the pilot
    band_to = Column(String(5), nullable=True)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)


class BillingRecord(Base):
    """The ERP's billing record — NOT a fiscal receipt (§4.5, decision 1.4)."""
    __tablename__ = "billing_records"
    __table_args__ = (
        CheckConstraint("medium IN ('electricity', 'water')", name="ck_billing_medium"),
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    session_id = Column(BigInteger, ForeignKey("sessions.id"), nullable=True)
    medium = Column(String(20), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False)
    unit_price = Column(Numeric(10, 4), nullable=False)
    vat_rate = Column(Numeric(5, 2), nullable=False)
    amount_net = Column(Numeric(10, 2), nullable=False)
    amount_gross = Column(Numeric(10, 2), nullable=False)
    tariff_id = Column(Integer, ForeignKey("tariffs.id"), nullable=False)
    issued_at = Column(DateTime, nullable=False, default=utcnow)
    exported_at = Column(DateTime, nullable=True)


class MarinaBillingPolicy(Base):
    """D9 numbers as configuration with defaults, not constants in code (§4.5)."""
    __tablename__ = "marina_billing_policy"

    marina_id = Column(Integer, ForeignKey("marinas.id", ondelete="CASCADE"), primary_key=True)
    min_start_amount = Column(Numeric(10, 2), nullable=False, default=1.00,
                              server_default=text("1.00"))
    allowed_negative = Column(Numeric(10, 2), nullable=False, default=-2.00,
                              server_default=text("-2.00"))
    low_credit_warn_pct = Column(Integer, nullable=False, default=20, server_default="20")
    note = Column(Text, nullable=True)
