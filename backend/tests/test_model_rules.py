"""Phase 3 model: the database enforces the rules of spec §4, on a MIGRATED database.

The probes live in scripts/schema_probes.py and run twice: here on SQLite built
by `alembic upgrade head` (not create_all — the migration is what production
gets), and in the boot check on PostgreSQL in CI.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
sys.path.insert(0, str(_REPO / "scripts"))
import schema_probes  # noqa: E402


@pytest.fixture(scope="module")
def migrated(tmp_path_factory):
    db = tmp_path_factory.mktemp("migrated") / "m.db"
    url = f"sqlite:///{db}"
    env = {**os.environ, "DATABASE_URL": url, "JWT_SECRET": "model-rules"}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       cwd=str(_BACKEND), env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    eng = create_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def results(migrated):
    """Run every probe ONCE; the parametrized test reads its own line."""
    return {name: (ok, detail) for name, ok, detail in schema_probes.run(migrated)}


def test_probe_list_is_not_empty():
    assert len(schema_probes.MUST_REFUSE) >= 10 and len(schema_probes.MUST_ALLOW) >= 3


@pytest.mark.parametrize("name", [n for n, _ in schema_probes.MUST_REFUSE + schema_probes.MUST_ALLOW])
def test_migrated_database_holds_the_rule(results, name):
    ok, detail = results[name]
    assert ok, f"{name}: {detail}"


def test_create_all_database_holds_the_same_rules(setup_test_database):
    """Tests build their database with create_all; it must have the same guards
    (the ledger trigger comes from a DDL event on the model)."""
    from tests.conftest import test_engine
    bad = [(n, d) for n, ok, d in schema_probes.run(test_engine) if not ok]
    assert bad == []


def test_no_price_column_on_measurement_tables(migrated):
    """The cabinet measures, the ERP prices — and only in billing_records (§12)."""
    insp = inspect(migrated)
    for table in ("sessions", "consumption_intervals", "outlets", "cabinets"):
        cols = {c["name"] for c in insp.get_columns(table)}
        assert not cols & {"estimated_cost", "cost", "price", "amount", "unit_price"}, table


def test_water_is_priced_per_litre(migrated):
    cols = {c["name"] for c in inspect(migrated).get_columns("sessions")}
    assert "water_liters" in cols and "water_m3" not in cols


def test_sessions_carry_erp_ref_and_may_exist_before_the_cabinet_knows(migrated):
    cols = {c["name"]: c for c in inspect(migrated).get_columns("sessions")}
    assert cols["erp_ref"]["nullable"] is False
    assert cols["cabinet_session_id"]["nullable"] is True
