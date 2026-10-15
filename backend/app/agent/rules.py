"""Detection rules — code with tests, not a prompt (D13 layer 3, spec §13.1).

Each rule reads the sliding window [since, now] and returns Findings. A Finding
becomes at most one alarm: its fingerprint is a hash of (rule, case key), and
the case key carries its own time bucket, so overlapping windows find the same
case again and the database's UNIQUE (fingerprint) keeps one row.

Everything read from a log is quoted into `evidence` as a value. No rule ever
branches on what a free-text field SAYS — only on which row it is in, and on
the structured columns around it (TC-ERP-AGT-06).

Rules with no ERP source yet (each is an open point in spec §11, not code that
pretends): an unknown NFC tag series, Smart Mode outside working hours, a door
together with a new device in the cabinet's LAN.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.engine import Connection

# Marina-local working hours: a socket command outside [06:00, 22:00) is odd.
WORK_FROM_HOUR, WORK_TO_HOUR = 6, 22
# How far back "never before" looks.
BASELINE = timedelta(days=30)
# Failed sign-ins from one address over this many different e-mails ...
SPRAY_ACCOUNTS = 3
# ... inside one bucket of this length.
SPRAY_BUCKET = timedelta(minutes=15)
# A quoted value is cut here: evidence, not a copy of the log.
QUOTE_MAX = 500

OUTLET_CMDS = ("controls.socket_cmd", "controls.water_cmd")


@dataclass
class Finding:
    rule_id: str
    case_key: str
    severity: str
    title: str
    why: str
    evidence: list = field(default_factory=list)
    window_from: datetime | None = None
    window_to: datetime | None = None

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(f"{self.rule_id}|{self.case_key}".encode()).hexdigest()


@dataclass(frozen=True)
class Rule:
    rule_id: str
    severity: str
    describe: str
    fn: Callable[[Connection, datetime, datetime], list]


def quote(v):
    """A value from a log, as evidence: kept as data, never interpreted, cut to QUOTE_MAX."""
    if v is None or isinstance(v, (int, float, bool)):
        return v
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [quote(x) for x in v[:50]]
    s = v if isinstance(v, str) else json.dumps(v, default=str, ensure_ascii=False)
    return s if len(s) <= QUOTE_MAX else s[:QUOTE_MAX] + "…"


def _as_dict(v) -> dict:
    """JSON columns come back as dict on PostgreSQL and as str on SQLite."""
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            out = json.loads(v)
        except ValueError:
            return {}
        return out if isinstance(out, dict) else {}
    return {}


def _dt(v) -> datetime:
    """SQLite gives text for a raw SELECT; PostgreSQL a datetime. Both are naive UTC (§4.0)."""
    return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))


def _p(c: Connection, **kw) -> dict:
    """Bind values. On SQLite a raw text() query compares strings, so a datetime is
    written exactly as SQLAlchemy's DateTime stores it there."""
    if c.dialect.name != "sqlite":
        return kw
    return {k: (v.strftime("%Y-%m-%d %H:%M:%S.%f") if isinstance(v, datetime) else v)
            for k, v in kw.items()}


def _ev(source: str, rows: list, fields: dict | None, observed_at) -> dict:
    return {"source": source, "row_ids": sorted({int(r) for r in rows}),
            "fields": {k: quote(v) for k, v in (fields or {}).items()},
            "observed_at": quote(observed_at)}


def _local_hour(at_utc: datetime, tz_name: str | None) -> tuple[int, str]:
    """Hour in the marina's zone; a zone this host cannot resolve falls back to UTC, said so."""
    name = tz_name or "UTC"
    if name.upper() == "UTC":
        tz, used = timezone.utc, "UTC"
    else:
        try:
            tz, used = ZoneInfo(name), name
        except (ZoneInfoNotFoundError, ValueError):
            tz, used = timezone.utc, f"UTC (zone {name!r} unknown to this host)"
    return at_utc.replace(tzinfo=timezone.utc).astimezone(tz).hour, used


# ─── the rules ───────────────────────────────────────────────────────────────

_DECOYS = text(
    "SELECT id, kind, decoy, method, path, source_ip, user_agent, observed_at "
    "FROM decoy_hits WHERE observed_at >= :since AND observed_at <= :now ORDER BY id")


def decoy_touch(c: Connection, since: datetime, now: datetime) -> list:
    """Layer 2: nobody legitimate touches a decoy — every touch is an attacker."""
    groups: dict = defaultdict(list)
    for r in c.execute(_DECOYS, _p(c, since=since, now=now)).mappings():
        at = _dt(r["observed_at"])
        groups[(r["kind"], r["decoy"], r["source_ip"], at.date().isoformat())].append((r, at))
    out = []
    for (kind, decoy, ip, day), hits in groups.items():
        first = hits[0][0]
        out.append(Finding(
            "decoy_touch", f"{kind}|{decoy}|{ip}|{day}", "critical",
            f"Decoy touched: {quote(decoy)}",
            f"{len(hits)} touch(es) of a '{kind}' decoy from {quote(ip) or 'an unknown address'}; "
            "nobody legitimate touches a decoy (layer 2).",
            [_ev("decoy_hits", [h["id"] for h, _ in hits],
                 {"kind": kind, "decoy": decoy, "method": first["method"], "path": first["path"],
                  "source_ip": ip, "user_agent": first["user_agent"]}, hits[0][1])],
            hits[0][1], hits[-1][1]))
    return out


_FAILED_LOGINS = text(
    "SELECT id, email_tried, detail, source_ip, created_at FROM auth_audit "
    "WHERE event = 'login_failed' AND created_at >= :since AND created_at <= :now "
    "AND source_ip IS NOT NULL ORDER BY id")


def login_spray(c: Connection, since: datetime, now: datetime) -> list:
    """Failed sign-ins over several different accounts from one address."""
    buckets: dict = defaultdict(list)
    step = int(SPRAY_BUCKET.total_seconds())
    for r in c.execute(_FAILED_LOGINS, _p(c, since=since, now=now)).mappings():
        at = _dt(r["created_at"])
        start = datetime.fromtimestamp(
            int(at.replace(tzinfo=timezone.utc).timestamp()) // step * step,
            tz=timezone.utc).replace(tzinfo=None)
        buckets[(r["source_ip"], start)].append((r, at))
    out = []
    for (ip, start), rows in buckets.items():
        emails = sorted({(r["email_tried"] or "").lower() for r, _ in rows})
        if len(emails) < SPRAY_ACCOUNTS:
            continue
        out.append(Finding(
            "login_spray", f"{ip}|{start.isoformat()}", "warning",
            f"Failed sign-ins on {len(emails)} accounts from one address",
            f"{len(rows)} failed sign-ins from {quote(ip)} on {len(emails)} different "
            f"e-mail addresses within {int(SPRAY_BUCKET.total_seconds() // 60)} min.",
            [_ev("auth_audit", [r["id"] for r, _ in rows],
                 {"source_ip": ip, "emails_tried": emails,
                  "details": sorted({r["detail"] or "" for r, _ in rows})}, rows[0][1])],
            start, start + SPRAY_BUCKET))
    return out


_OUTLET_CMDS_IN_WINDOW = text(
    "SELECT a.id, a.cabinet_id, a.endpoint_key, a.action, a.actor_ref, a.reason, a.source_ip, "
    "a.created_at, c.display_id, m.timezone FROM command_audit a "
    "JOIN cabinets c ON c.id = a.cabinet_id JOIN marinas m ON m.id = c.marina_id "
    "WHERE a.actor_type = 'operator' AND a.endpoint_key IN ('controls.socket_cmd', "
    "'controls.water_cmd') AND a.created_at >= :since AND a.created_at <= :now ORDER BY a.id")


def socket_cmd_odd_hour(c: Connection, since: datetime, now: datetime) -> list:
    """An outlet switched by an operator outside marina working hours."""
    out = []
    for r in c.execute(_OUTLET_CMDS_IN_WINDOW, _p(c, since=since, now=now)).mappings():
        at = _dt(r["created_at"])
        hour, zone = _local_hour(at, r["timezone"])
        if WORK_FROM_HOUR <= hour < WORK_TO_HOUR:
            continue
        out.append(Finding(
            "socket_cmd_odd_hour", f"command_audit|{r['id']}", "warning",
            f"{r['display_id']}: outlet command outside working hours",
            f"{r['endpoint_key']} '{quote(r['action'])}' at {hour:02d}:00 local time "
            f"({zone}); working hours are {WORK_FROM_HOUR:02d}–{WORK_TO_HOUR:02d} h.",
            [_ev("command_audit", [r["id"]],
                 {"endpoint_key": r["endpoint_key"], "action": r["action"],
                  "actor_ref": r["actor_ref"], "reason": r["reason"], "source_ip": r["source_ip"],
                  "local_hour": hour, "zone": zone}, at)],
            at, at))
    return out


_ACTOR_HISTORY = text(
    "SELECT id, endpoint_key, source_ip FROM command_audit "
    "WHERE actor_ref = :actor AND created_at >= :from_at AND created_at < :before")


def _history(c: Connection, actor: str, before: datetime) -> list:
    return list(c.execute(_ACTOR_HISTORY, _p(c, actor=actor, from_at=before - BASELINE, before=before)).mappings())


def socket_cmd_new_ip(c: Connection, since: datetime, now: datetime) -> list:
    """An outlet switched from an address this account never used before (30 days)."""
    out = []
    for r in c.execute(_OUTLET_CMDS_IN_WINDOW, _p(c, since=since, now=now)).mappings():
        if not r["actor_ref"] or not r["source_ip"]:
            continue
        at = _dt(r["created_at"])
        hist = _history(c, r["actor_ref"], at)
        if not hist or any(h["source_ip"] == r["source_ip"] for h in hist):
            continue      # no baseline yet, or a known address
        known = sorted({h["source_ip"] for h in hist if h["source_ip"]})
        out.append(Finding(
            "socket_cmd_new_ip", f"command_audit|{r['id']}", "warning",
            f"{r['display_id']}: outlet command from a new address",
            f"In the last {BASELINE.days} days the account sent commands from {len(known)} "
            "addresses; this is not one of them.",
            [_ev("command_audit", [r["id"]],
                 {"endpoint_key": r["endpoint_key"], "action": r["action"],
                  "actor_ref": r["actor_ref"], "source_ip": r["source_ip"],
                  "known_ips": known}, at),
             _ev("command_audit", [h["id"] for h in hist], {"baseline_days": BASELINE.days}, None)],
            at, at))
    return out


_ALL_CMDS_IN_WINDOW = text(
    "SELECT a.id, a.endpoint_key, a.actor_ref, a.source_ip, a.created_at FROM command_audit a "
    "WHERE a.actor_ref IS NOT NULL AND a.created_at >= :since AND a.created_at <= :now "
    "ORDER BY a.id")


def account_new_endpoint(c: Connection, since: datetime, now: datetime) -> list:
    """An account calls an endpoint it never called before (30 days), while it has history."""
    out, seen = [], set()
    for r in c.execute(_ALL_CMDS_IN_WINDOW, _p(c, since=since, now=now)).mappings():
        at = _dt(r["created_at"])
        key = (r["actor_ref"], r["endpoint_key"], at.date())
        if key in seen:
            continue
        hist = _history(c, r["actor_ref"], at)
        if not hist or any(h["endpoint_key"] == r["endpoint_key"] for h in hist):
            continue
        seen.add(key)
        out.append(Finding(
            "account_new_endpoint", f"{r['actor_ref']}|{r['endpoint_key']}|{at.date()}", "info",
            f"Account calls {r['endpoint_key']} for the first time",
            f"In the last {BASELINE.days} days the account called {len({h['endpoint_key'] for h in hist})}"
            " other kinds of command, never this one.",
            [_ev("command_audit", [r["id"]],
                 {"endpoint_key": r["endpoint_key"], "actor_ref": r["actor_ref"],
                  "source_ip": r["source_ip"],
                  "known_endpoints": sorted({h["endpoint_key"] for h in hist})}, at)],
            at, at))
    return out


_DOOR_ALARMS = text(
    "SELECT a.id, a.cabinet_id, a.alarm_data, a.received_at, c.display_id FROM alarm_log a "
    "JOIN cabinets c ON c.id = a.cabinet_id "
    "WHERE a.received_at >= :since AND a.received_at <= :now ORDER BY a.id")
_STATUS_SNAPSHOTS = text(
    "SELECT p.id, p.marina_id, p.cache_key, p.last_seen_data, p.last_synced_at "
    "FROM pedestal_cache p WHERE p.cache_key LIKE 'pedestals.status_ext:%' "
    "AND p.last_synced_at >= :since AND p.last_synced_at <= :now ORDER BY p.id")
_CABINETS_OF_MARINA = text(
    "SELECT id, pedestal_pk, display_id FROM cabinets WHERE marina_id = :m")
_WINDOW_COVERS = text(
    "SELECT id FROM service_windows WHERE cabinet_id = :cab AND from_at <= :at AND to_at >= :at")


def _snapshot_cabinet(c: Connection, marina_id: int, cache_key: str):
    # 'pedestals.status_ext:/api/ext/pedestals/<ref>/status' — <ref> is the PK or display_id
    parts = cache_key.split("/")
    ref = parts[-2] if len(parts) >= 2 else ""
    for cab in c.execute(_CABINETS_OF_MARINA, {"m": marina_id}).mappings():
        if ref in (str(cab["pedestal_pk"]), cab["display_id"]):
            return cab
    return None


def door_no_window(c: Connection, since: datetime, now: datetime) -> list:
    """The cabinet door, with no announced service window (D16, §7.1)."""
    out = []
    for r in c.execute(_DOOR_ALARMS, _p(c, since=since, now=now)).mappings():
        payload = _as_dict(r["alarm_data"])
        if payload.get("event") != "marina_door":
            continue
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        if str(data.get("door_state") or data.get("state") or "").lower() == "closed":
            continue
        at = _dt(r["received_at"])
        if c.execute(_WINDOW_COVERS, _p(c, cab=r["cabinet_id"], at=at)).first():
            continue
        out.append(Finding(
            "door_no_window", f"alarm_log|{r['id']}", "warning",
            f"{r['display_id']}: door open outside a service window",
            "The cabinet reported its door (marina_door) and no service window was "
            "announced for that time.",
            [_ev("alarm_log", [r["id"]], {"event": "marina_door", "data": data}, at)], at, at))
    for r in c.execute(_STATUS_SNAPSHOTS, _p(c, since=since, now=now)).mappings():
        data = _as_dict(r["last_seen_data"])
        if str(data.get("door_state") or "").lower() != "open":
            continue
        cab = _snapshot_cabinet(c, r["marina_id"], r["cache_key"])
        if cab is None:
            continue
        at = _dt(r["last_synced_at"])
        if c.execute(_WINDOW_COVERS, _p(c, cab=cab["id"], at=at)).first():
            continue
        hour = at.replace(minute=0, second=0, microsecond=0)
        out.append(Finding(
            "door_no_window", f"status_ext|{cab['id']}|{hour.isoformat()}", "warning",
            f"{cab['display_id']}: door open outside a service window",
            "The cabinet's last state (status_ext) says door_state = open and no service "
            "window was announced for that time.",
            [_ev("pedestal_cache", [r["id"]], {"cache_key": r["cache_key"],
                                               "door_state": data.get("door_state")}, at)],
            at, at))
    return out


RULES = (
    Rule("decoy_touch", "critical", "a decoy is touched (layer 2)", decoy_touch),
    Rule("login_spray", "warning",
         f"failed sign-ins on ≥{SPRAY_ACCOUNTS} accounts from one address within "
         f"{int(SPRAY_BUCKET.total_seconds() // 60)} min", login_spray),
    Rule("socket_cmd_odd_hour", "warning",
         f"outlet command outside {WORK_FROM_HOUR:02d}–{WORK_TO_HOUR:02d} h local time",
         socket_cmd_odd_hour),
    Rule("socket_cmd_new_ip", "warning",
         f"outlet command from an address the account has not used in {BASELINE.days} days",
         socket_cmd_new_ip),
    Rule("account_new_endpoint", "info",
         f"account calls an endpoint it has not called in {BASELINE.days} days", account_new_endpoint),
    Rule("door_no_window", "warning", "cabinet door outside an announced service window",
         door_no_window),
)
RULE_IDS = tuple(r.rule_id for r in RULES)
