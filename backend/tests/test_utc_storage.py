"""Every stored time is UTC (spec §4.0, your decision 2026-10-12).

Naive UTC and naive local time look the same in the database, so the rule is
checked by behaviour: the real write paths run in a process whose local zone
is UTC+14 (tests/utc_scenario.py), and every non-null DateTime in every table
is read back. A local time would be 14 hours off; 2 are allowed.

The test cannot pass empty: it fails if the child process is not really at
+14 h, and if fewer columns were written than the list below.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.utils.time import AwareDatetimeError, parse_utc, to_naive_utc

BACKEND = Path(__file__).resolve().parent.parent

# Columns the scenario must have written. A path that stops writing (or a scenario
# step that silently stops running) shrinks this, and the test says which.
MUST_BE_SEEN = {
    "users.created_at", "users.last_login", "marinas.created_at", "marinas.updated_at",
    "cabinets.created_at", "cabinets.last_heartbeat_at", "cabinets.last_polled_at",
    "cabinet_capabilities.checked_at", "berths.created_at", "berth_outlets.assigned_at",
    "mapping_comparison.checked_at", "outlet_nfc_tags.provisioned_at",
    "customers.created_at", "credit_ledger.created_at",
    "sessions.created_at", "sessions.activated_at", "sessions.ended_at",
    "sessions.reconciled_at", "sessions.ack_sent_at",
    "consumption_intervals.from_at", "consumption_intervals.to_at",
    "outlet_meter_state.read_at", "reconciliation_runs.started_at",
    "reconciliation_runs.finished_at", "reconciliation_runs.window_from",
    "reconciliation_runs.window_to", "command_audit.created_at", "command_audit.completed_at",
    "audit_log.performed_at", "alarm_log.received_at", "session_log.recorded_at",
    "sync_log.started_at", "sync_log.completed_at", "pedestal_cache.last_synced_at",
}


@pytest.fixture(scope="module")
def report():
    env = {**os.environ, "TZ": "XXX-14", "PYTHONPATH": str(BACKEND)}
    for k in ("DATABASE_URL", "COLLECTOR_ENABLED"):
        env.pop(k, None)
    r = subprocess.run([sys.executable, str(BACKEND / "tests" / "utc_scenario.py")],
                       cwd=str(BACKEND), env=env, capture_output=True, text=True, timeout=300)
    line = next((x for x in r.stdout.splitlines() if x.startswith("UTC_REPORT ")), None)
    assert r.returncode == 0 and line, f"scenario failed:\n{r.stdout[-2000:]}\n{r.stderr[-3000:]}"
    return json.loads(line[len("UTC_REPORT "):])


def test_the_scenario_really_ran_at_utc_plus_14(report):
    assert report["local_offset_h"] == pytest.approx(14, abs=0.1), (
        "the child process is not at UTC+14, so this test would prove nothing")


def test_every_stored_time_is_utc_not_local(report):
    assert report["bad"] == []


def test_every_write_path_was_exercised(report):
    missing = sorted(MUST_BE_SEEN - set(report["seen"]))
    assert missing == [], f"never written by the scenario: {missing}"


def test_an_aware_datetime_is_refused_at_flush():
    """PostgreSQL would drop the offset of 12:00+02:00 and store 12:00 — 2 h wrong."""
    from tests.conftest import TestSession
    from app.models.billing import Customer
    db = TestSession()
    try:
        aware = datetime(2026, 10, 12, 12, 0, tzinfo=timezone(timedelta(hours=2)))
        db.add(Customer(marina_id=1, full_name="Aware", created_at=aware))
        with pytest.raises(AwareDatetimeError, match="naive UTC"):
            db.flush()
    finally:
        db.rollback()
        db.close()


def test_cabinet_times_are_converted_not_stripped():
    ten_utc = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    assert parse_utc("2026-10-12T10:00:00Z") == ten_utc
    assert parse_utc("2026-10-12T12:00:00+02:00") == ten_utc     # converted, not stripped
    assert parse_utc("2026-10-12T10:00:00") == ten_utc
    assert parse_utc(None) is None
    with pytest.raises(ValueError):
        to_naive_utc(ten_utc)                            # naive: zone unknown
