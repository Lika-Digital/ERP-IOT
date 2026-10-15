"""One pass of the agent: every rule over the sliding window, then alarms or shadow lines.

No state of its own (spec §13.1): no cursor, no "last seen". Each pass looks at
[now - window, now] and writes `INSERT ... ON CONFLICT (fingerprint) DO NOTHING`
— that needs the INSERT privilege only; DO UPDATE would need UPDATE, so it is
not here. The overlap costs CPU, never a second alarm.

A rule an Admin has not switched to 'active' runs in the SHADOW: it only logs
what it would have opened (D13: "proposes -> runs in the shadow -> a human
approves -> active"). The agent never changes a rule's mode itself.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .rules import RULES, Finding, _p

log = logging.getLogger("erp-agent")

DEFAULT_WINDOW = timedelta(hours=24)

_MODES = text("SELECT rule_id, mode FROM security_rule_settings")
_INSERT_PG = text(
    "INSERT INTO security_alarms (rule_id, fingerprint, severity, title, why, evidence, "
    "window_from, window_to, created_at, state, simulated) VALUES (:rule_id, :fingerprint, "
    ":severity, :title, :why, CAST(:evidence AS JSONB), :window_from, :window_to, :created_at, "
    "'open', :simulated) "
    "ON CONFLICT (fingerprint) DO NOTHING")
_INSERT_SQLITE = text(
    "INSERT INTO security_alarms (rule_id, fingerprint, severity, title, why, evidence, "
    "window_from, window_to, created_at, state, simulated) VALUES (:rule_id, :fingerprint, "
    ":severity, :title, :why, :evidence, :window_from, :window_to, :created_at, 'open', "
    ":simulated) "
    "ON CONFLICT (fingerprint) DO NOTHING")


def utcnow() -> datetime:
    """Naive UTC, the contract of every DateTime column (spec §4.0)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _insert(c: Connection, f: Finding, now: datetime) -> bool:
    stmt = _INSERT_PG if c.dialect.name == "postgresql" else _INSERT_SQLITE
    r = c.execute(stmt, _p(
        c, rule_id=f.rule_id, fingerprint=f.fingerprint, severity=f.severity,
        title=f.title, why=f.why,
        evidence=json.dumps(f.evidence, default=str, ensure_ascii=False),
        window_from=f.window_from, window_to=f.window_to, created_at=now,
        simulated=bool(f.simulated)))
    return r.rowcount == 1


def run_once(c: Connection, now: datetime | None = None,
             window: timedelta = DEFAULT_WINDOW) -> dict:
    """Every rule once. Returns {rule_id: {"mode", "found", "opened"}}; commits."""
    now = now or utcnow()
    since = now - window
    modes = {r: m for r, m in c.execute(_MODES)}
    out = {}
    for rule in RULES:
        mode = modes.get(rule.rule_id, "shadow")
        findings = rule.fn(c, since, now)
        opened = 0
        for f in findings:
            if mode == "active":
                opened += _insert(c, f, now)
            else:
                log.info("shadow rule=%s fingerprint=%s severity=%s title=%s",
                         f.rule_id, f.fingerprint[:16], f.severity, f.title)
        out[rule.rule_id] = {"mode": mode, "found": len(findings), "opened": opened}
    c.commit()
    return out
