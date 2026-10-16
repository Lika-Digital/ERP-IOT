"""Probes that the DATABASE enforces the rules of spec §4 (phases 3 and 4) — not just the code.

`alembic check` compares tables, columns and indexes, but not CHECK
constraints or triggers. These probes try to break each rule on a migrated
database and expect the database to refuse. Every probe runs in its own
transaction and is rolled back, so the database is left as it was.

Used by scripts/boot_check.py (PostgreSQL in CI, SQLite locally) and by
backend/tests/test_model_rules.py (migrated SQLite).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Connection, Engine

# naive UTC, the contract of every DateTime column (app/utils/time.py)
NOW = datetime(2026, 10, 12, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)


def _setup(c: Connection) -> dict:
    """One marina, one full cabinet with Q1, Q2 and V1, two berths, one customer."""
    def one(sql: str, **kw):
        return c.execute(text(sql + " RETURNING id"), kw).scalar_one()

    ids = {}
    ids["marina"] = one(
        "INSERT INTO marinas (name, timezone, pedestal_api_base_url, status, created_at, updated_at) "
        "VALUES ('probe', 'UTC', 'http://x', 'active', :t, :t)", t=NOW)
    ids["cabinet"] = one(
        "INSERT INTO cabinets (marina_id, pedestal_pk, display_id, device_type, base_url, "
        "service_email, service_pw_enc, created_at) "
        "VALUES (:m, 1, 'MAR_PROBE_01', 'full', 'http://x', 'e@x', 'enc', :t)",
        m=ids["marina"], t=NOW)
    for name, medium in (("Q1", "electricity"), ("Q2", "electricity"), ("V1", "water")):
        ids[name] = one("INSERT INTO outlets (cabinet_id, outlet_name, medium) VALUES (:c, :n, :m)",
                        c=ids["cabinet"], n=name, m=medium)
    for b in ("A1", "A2"):
        ids[b] = one("INSERT INTO berths (marina_id, berth_number, created_at) VALUES (:m, :b, :t)",
                     m=ids["marina"], b=b, t=NOW)
    ids["customer"] = one(
        "INSERT INTO customers (marina_id, full_name, created_at) VALUES (:m, 'P', :t)",
        m=ids["marina"], t=NOW)
    return ids


def _assign(c, berth, outlet, medium, by="probe@lika"):
    c.execute(text("INSERT INTO berth_outlets (berth_id, outlet_id, medium, source, assigned_by, "
                   "assigned_at) VALUES (:b, :o, :m, 'erp_manual', :by, :t)"),
              dict(b=berth, o=outlet, m=medium, by=by, t=NOW))


def _ledger(c, cust, delta, bal, reason="topup", by="recepcija@x", session=None):
    c.execute(text("INSERT INTO credit_ledger (customer_id, delta, reason, session_id, "
                   "balance_after, created_by, created_at) VALUES (:c, :d, :r, :s, :b, :by, :t)"),
              dict(c=cust, d=delta, r=reason, s=session, b=bal, by=by, t=NOW))


# Each probe: (name, function(conn, ids) that MUST raise)
def _p_ledger_update(c, i):
    _ledger(c, i["customer"], 10, 10)
    c.execute(text("UPDATE credit_ledger SET delta = 999"))


def _p_ledger_delete(c, i):
    _ledger(c, i["customer"], 10, 10)
    c.execute(text("DELETE FROM credit_ledger"))


def _p_blank_assigned_by(c, i):
    _assign(c, i["A1"], i["Q1"], "electricity", by="   ")


def _p_electric_outlet_two_berths(c, i):
    _assign(c, i["A1"], i["Q1"], "electricity")
    _assign(c, i["A2"], i["Q1"], "electricity")


def _p_berth_two_electric_outlets(c, i):
    _assign(c, i["A1"], i["Q1"], "electricity")
    _assign(c, i["A1"], i["Q2"], "electricity")


def _p_medium_lie(c, i):
    # claim a valve is electricity, to dodge the uniqueness: the composite FK refuses
    _assign(c, i["A1"], i["V1"], "electricity")


def _p_bare_digit_outlet(c, i):
    c.execute(text("INSERT INTO outlets (cabinet_id, outlet_name, medium) VALUES (:c, '1', 'electricity')"),
              dict(c=i["cabinet"]))


def _p_water_on_q(c, i):
    c.execute(text("INSERT INTO outlets (cabinet_id, outlet_name, medium) VALUES (:c, 'Q3', 'water')"),
              dict(c=i["cabinet"]))


def _p_operator_without_reason(c, i):
    c.execute(text("INSERT INTO command_audit (cabinet_id, endpoint_key, action, actor_type, "
                   "request_url, created_at) VALUES (:c, 'controls.socket_cmd', 'activate', "
                   "'operator', 'http://x', :t)"), dict(c=i["cabinet"], t=NOW))


def _p_billed_without_figure(c, i):
    c.execute(text("INSERT INTO sessions (erp_ref, cabinet_id, outlet_id, session_type, status, "
                   "billing_state, created_at) VALUES ('r1', :c, :o, 'electricity', 'ended', "
                   "'billed', :t)"), dict(c=i["cabinet"], o=i["Q1"], t=NOW))


def _p_consumption_without_session(c, i):
    _ledger(c, i["customer"], -1, -1, reason="consumption", session=None)


def _session(c, i, ref="r1", billing="pending", reconciled=None, energy=None):
    return c.execute(text(
        "INSERT INTO sessions (erp_ref, cabinet_id, outlet_id, session_type, status, energy_kwh, "
        "billing_state, reconciled_at, created_at) VALUES (:r, :c, :o, 'electricity', 'ended', "
        ":e, :b, :rec, :t) RETURNING id"),
        dict(r=ref, c=i["cabinet"], o=i["Q1"], e=energy, b=billing, rec=reconciled, t=NOW)
    ).scalar_one()


def _interval(c, i, session=None, standalone=False, frm=NOW, to=None, kwh=0.5):
    from datetime import timedelta
    c.execute(text("INSERT INTO consumption_intervals (outlet_id, session_id, standalone, from_at, "
                   "to_at, energy_kwh, source) VALUES (:o, :s, :st, :f, :t, :e, 'register')"),
              dict(o=i["Q1"], s=session, st=standalone, f=frm,
                   t=to or frm + timedelta(minutes=1), e=kwh))


def _p_billed_not_reconciled(c, i):
    # D7: a figure from the webhook alone is never billed
    _session(c, i, billing="billed", energy=3.25, reconciled=None)


def _p_standalone_with_session(c, i):
    # D19: consumption while the cabinet runs on its own is never an ERP session
    _interval(c, i, session=_session(c, i), standalone=True)


def _p_interval_backwards(c, i):
    _interval(c, i, to=NOW)


def _p_interval_negative(c, i):
    _interval(c, i, kwh=-0.1)


def _p_hmac_without_secret(c, i):
    c.execute(text("UPDATE cabinets SET webhook_hmac = :t WHERE id = :c"),
              dict(t=True, c=i["cabinet"]))


def _p_alarm_twice(c, i):
    for _ in range(2):
        c.execute(text("INSERT INTO alarm_log (marina_id, pedestal_id, alarm_data, received_at, "
                       "cabinet_id, cabinet_alarm_id, source) VALUES (:m, 1, '{}', :t, :c, 7, "
                       "'poll')"), dict(m=i["marina"], t=NOW, c=i["cabinet"]))


def _p_user(c, role="admin", confirmed=None, secret=None, failed=0, email="probe@d20"):
    """D20 (spec §4.9): two roles, 2FA confirmed only with a secret."""
    return c.execute(text(
        "INSERT INTO users (email, role, is_active, created_at, totp_secret_enc, "
        "totp_confirmed_at, failed_count) VALUES (:e, :r, true, :t, :s, :conf, :f) RETURNING id"),
        dict(e=email, r=role, t=NOW, s=secret, conf=confirmed, f=failed)).scalar_one()


def _setup_token(c, uid, h="a" * 64, expires=None):
    c.execute(text("INSERT INTO setup_tokens (token_hash, user_id, created_at, expires_at) "
                   "VALUES (:h, :u, :t, :x)"), dict(h=h, u=uid, t=NOW, x=expires or NOW.replace(hour=13)))


def _p_setup_backwards(c, i):
    _setup_token(c, _p_user(c), expires=NOW.replace(hour=11))


def _p_setup_twice(c, i):
    uid = _p_user(c)
    _setup_token(c, uid)
    _setup_token(c, uid)


# ─── D21 (spec §13.1) ────────────────────────────────────────────────────────

def _alarm(c, state="open", by=None, at=None, severity="warning", fp="f" * 64):
    c.execute(text("INSERT INTO security_alarms (rule_id, fingerprint, severity, title, why, "
                   "evidence, created_at, state, decided_by, decided_at) VALUES ('probe', :fp, "
                   ":sev, 't', 'w', '[]', :t, :st, :by, :at)"),
              dict(fp=fp, sev=severity, t=NOW, st=state, by=by, at=at))


def _p_security_alarm_twice(c, i):
    _alarm(c)
    _alarm(c)          # same fingerprint: the agent's ON CONFLICT relies on this UNIQUE


# ── D28: the demo marina — real and simulated never mix where it costs ─────────

SIM_URL = "http://127.0.0.1:18080/c/SIM_A_02"


def _cabinet(c, i, pk=2, url="http://y", sim=False, disp="MAR_PROBE_02"):
    return c.execute(text(
        "INSERT INTO cabinets (marina_id, pedestal_pk, display_id, device_type, base_url, "
        "service_email, service_pw_enc, created_at, is_simulated) "
        "VALUES (:m, :pk, :d, 'full', :u, 'e@x', 'enc', :t, :s) RETURNING id"),
        dict(m=i["marina"], pk=pk, d=disp, u=url, t=NOW, s=sim)).scalar_one()


def _billing(c, i, session=None, customer=None):
    tariff = c.execute(text(
        "INSERT INTO tariffs (marina_id, medium, unit_price, vat_rate, valid_from) "
        "VALUES (:m, 'electricity', 0.3, 25, '2026-10-01') RETURNING id"),
        dict(m=i["marina"])).scalar_one()
    c.execute(text(
        "INSERT INTO billing_records (customer_id, session_id, medium, quantity, unit_price, "
        "vat_rate, amount_net, amount_gross, tariff_id, issued_at) VALUES (:c, :s, "
        "'electricity', 1, 0.3, 25, 0.3, 0.38, :t, :at)"),
        dict(c=customer or i["customer"], s=session, t=tariff, at=NOW))


def _demo_customer(c, i):
    return c.execute(text(
        "INSERT INTO customers (marina_id, full_name, created_at, is_demo) "
        "VALUES (:m, 'Demo', :t, :d) RETURNING id"), dict(m=i["marina"], t=NOW, d=True)).scalar_one()


def _sim_session(c, i):
    cab = _cabinet(c, i, url=SIM_URL, sim=True, disp="SIM_A_02")
    q1 = c.execute(text("INSERT INTO outlets (cabinet_id, outlet_name, medium) "
                        "VALUES (:c, 'Q1', 'electricity') RETURNING id"), dict(c=cab)).scalar_one()
    return c.execute(text(
        "INSERT INTO sessions (erp_ref, cabinet_id, outlet_id, session_type, status, energy_kwh, "
        "billing_state, reconciled_at, created_at) VALUES ('sim1', :c, :o, 'electricity', "
        "'ended', 1, 'pending', :t, :t) RETURNING id"), dict(c=cab, o=q1, t=NOW)).scalar_one()


def _vessel(c, i, name="Probe"):
    return c.execute(text("INSERT INTO vessels (marina_id, name, created_at, created_by) "
                          "VALUES (:m, :n, :t, 'probe') RETURNING id"),
                     dict(m=i["marina"], n=name, t=NOW)).scalar_one()


def _berth_vessel(c, i, vessel, frm=NOW, to=None):
    c.execute(text("INSERT INTO berth_vessels (berth_id, vessel_id, valid_from, valid_to, "
                   "assigned_by) VALUES (:b, :v, :f, :t, 'probe')"),
              dict(b=i["A1"], v=vessel, f=frm, t=to))


def _p_two_current_vessels(c, i):
    _berth_vessel(c, i, _vessel(c, i))
    _berth_vessel(c, i, _vessel(c, i, "Second"))


def _p_vessel_history(c, i):
    from datetime import timedelta
    _berth_vessel(c, i, _vessel(c, i), frm=NOW - timedelta(days=30), to=NOW - timedelta(days=1))
    _berth_vessel(c, i, _vessel(c, i, "Now"))


def _map(c, i, name):
    c.execute(text("UPDATE marinas SET map_svg = :n WHERE id = :m"), dict(n=name, m=i["marina"]))


def _p_window_backwards(c, i):
    c.execute(text("INSERT INTO service_windows (cabinet_id, from_at, to_at, announced_by, "
                   "created_at) VALUES (:c, :t, :t, 'serviser', :t)"), dict(c=i["cabinet"], t=NOW))


MUST_REFUSE: list[tuple[str, Callable]] = [
    ("credit_ledger: UPDATE is refused (append-only)", _p_ledger_update),
    ("credit_ledger: DELETE is refused (append-only)", _p_ledger_delete),
    ("credit_ledger: consumption row without a session", _p_consumption_without_session),
    ("berth_outlets: blank assigned_by", _p_blank_assigned_by),
    ("berth_outlets: one electricity outlet on two berths", _p_electric_outlet_two_berths),
    ("berth_outlets: two electricity outlets on one berth", _p_berth_two_electric_outlets),
    ("berth_outlets: a valve claimed as electricity", _p_medium_lie),
    ("outlets: a bare digit as outlet name", _p_bare_digit_outlet),
    ("outlets: water on a Q outlet", _p_water_on_q),
    ("command_audit: operator command without a reason", _p_operator_without_reason),
    ("sessions: billed without a figure (NULL is not 0)", _p_billed_without_figure),
    ("sessions: billed before the pull reconciled it (D7)", _p_billed_not_reconciled),
    ("consumption_intervals: standalone AND on an ERP session (D19)", _p_standalone_with_session),
    ("consumption_intervals: to_at not after from_at", _p_interval_backwards),
    ("consumption_intervals: a negative register difference", _p_interval_negative),
    ("cabinets: HMAC switched on without a secret", _p_hmac_without_secret),
    ("alarm_log: the same cabinet alarm stored twice", _p_alarm_twice),
    ("users: a role D20 does not know (super_admin is gone)", lambda c, i: _p_user(c, role="super_admin")),
    ("users: 2FA confirmed without a secret", lambda c, i: _p_user(c, confirmed=NOW)),
    ("users: a negative failure count", lambda c, i: _p_user(c, failed=-1)),
    ("setup_tokens: a link that expires before it is made", _p_setup_backwards),
    ("setup_tokens: the same token hash twice", _p_setup_twice),
    ("security_alarms: the same fingerprint twice (D21: one case, one alarm)",
     _p_security_alarm_twice),
    ("security_alarms: a severity the agent does not know", lambda c, i: _alarm(c, severity="high")),
    ("security_alarms: closed without who and when", lambda c, i: _alarm(c, state="closed")),
    ("security_alarms: open but carrying a decision",
     lambda c, i: _alarm(c, at=NOW)),
    ("service_windows: a window that ends when it starts", _p_window_backwards),
    # D28
    ("cabinets: a simulated cabinet at a real address",
     lambda c, i: _cabinet(c, i, url="http://100.64.0.9", sim=True)),
    ("cabinets: a real cabinet at the simulator's address",
     lambda c, i: _cabinet(c, i, url=SIM_URL, sim=False)),
    ("cabinets: the same pedestal twice on one cabinet server",
     lambda c, i: _cabinet(c, i, pk=1, url="http://x")),
    ("berth_reservations: a reservation that ends when it starts",
     lambda c, i: c.execute(text(
         "INSERT INTO berth_reservations (berth_id, starts_at, ends_at, created_by, created_at) "
         "VALUES (:b, :t, :t, 'probe', :t)"), dict(b=i["A1"], t=NOW))),
    ("billing_records: a demo customer is never billed (D28)",
     lambda c, i: _billing(c, i, customer=_demo_customer(c, i))),
    ("billing_records: a session from a simulated cabinet is never billed (D28)",
     lambda c, i: _billing(c, i, session=_sim_session(c, i))),
    ("credit_ledger: a demo customer has no ledger (D28)",
     lambda c, i: _ledger(c, _demo_customer(c, i), 10, 10)),
    # D23
    ("marinas: a map that is a path, not a file name",
     lambda c, i: _map(c, i, "../../etc/x.svg")),
    ("marinas: a map that is not an .svg",
     lambda c, i: _map(c, i, "map.html")),
    # D27 phase 1
    ("vessels: a vessel without a name", lambda c, i: _vessel(c, i, name="  ")),
    ("berth_vessels: two current vessels on one berth", _p_two_current_vessels),
    ("berth_vessels: a period that ends before it starts",
     lambda c, i: _berth_vessel(c, i, _vessel(c, i), frm=NOW, to=NOW)),
    ("security_agent_passes: a negative count",
     lambda c, i: c.execute(text("INSERT INTO security_agent_passes (finished_at, rules, opened) "
                                 "VALUES (:t, 7, -1)"), dict(t=NOW))),
]


def _p_valve_shared(c, i):
    _assign(c, i["A1"], i["V1"], "water")
    _assign(c, i["A2"], i["V1"], "water")


def _p_contract_default_prepaid(c, i):
    c.execute(text("INSERT INTO contracts (customer_id, valid_from) VALUES (:c, '2026-10-01')"),
              dict(c=i["customer"]))
    mode = c.execute(text("SELECT billing_mode FROM contracts")).scalar_one()
    assert mode == "prepaid", mode


def _p_policy_defaults(c, i):
    c.execute(text("INSERT INTO marina_billing_policy (marina_id) VALUES (:m)"), dict(m=i["marina"]))
    row = c.execute(text("SELECT min_start_amount, allowed_negative, low_credit_warn_pct "
                         "FROM marina_billing_policy")).one()
    assert (float(row[0]), float(row[1]), int(row[2])) == (1.0, -2.0, 20), row


def _p_interval_standalone(c, i):
    _interval(c, i, standalone=True)


def _p_billed_reconciled(c, i):
    _session(c, i, billing="billed", energy=3.25, reconciled=NOW)


MUST_ALLOW: list[tuple[str, Callable]] = [
    ("marinas: a map file name under /maps/ (D23)", lambda c, i: _map(c, i, "demo-marina.svg")),
    ("berth_vessels: a past vessel and a current one on the same berth (D27)", _p_vessel_history),
    ("berth_outlets: a valve MAY be shared between berths (D1)", _p_valve_shared),
    ("contracts: billing_mode defaults to prepaid in the database (D9)", _p_contract_default_prepaid),
    ("marina_billing_policy: defaults 1.00 / -2.00 / 20 %", _p_policy_defaults),
    ("consumption_intervals: standalone consumption WITHOUT a session is kept (D19)",
     _p_interval_standalone),
    ("sessions: billed once reconciled, with a figure", _p_billed_reconciled),
    ("users: an admin with no password yet (one-time link, D20.3) and no 2FA",
     lambda c, i: _p_user(c)),
    ("users: a marina manager with 2FA confirmed", lambda c, i: _p_user(
        c, role="marina_manager", secret="enc", confirmed=NOW)),
    ("security_alarms: an open alarm, with no decision", lambda c, i: _alarm(c)),
    # D28
    ("cabinets: pedestal 1 on two cabinet servers in one marina (Krk and marina-iot)",
     lambda c, i: _cabinet(c, i, pk=1, url="http://100.64.0.9")),
    ("cabinets: a simulated cabinet at the simulator's address",
     lambda c, i: _cabinet(c, i, url=SIM_URL, sim=True, disp="SIM_A_02")),
    ("billing_records: a real customer's real session is billed",
     lambda c, i: _billing(c, i, session=_session(c, i, billing="billed", energy=1,
                                                  reconciled=NOW))),
]


def _sqlite_fk(c: Connection) -> None:
    if c.dialect.name == "sqlite":
        c.exec_driver_sql("PRAGMA foreign_keys=ON")
        c.commit()          # the PRAGMA autobegan a transaction; close it before begin()


def run(engine: Engine) -> list[tuple[str, bool, str]]:
    results = []
    for name, probe in MUST_REFUSE:
        with engine.connect() as c:
            _sqlite_fk(c)
            tx = c.begin()
            try:
                ids = _setup(c)
                try:
                    probe(c, ids)
                    results.append((name, False, "the database ACCEPTED it"))
                except Exception as exc:  # noqa: BLE001 — judged below
                    # Only a real refusal counts. A typo in a probe's SQL raises too,
                    # and must not pass as "the database refused it".
                    # PostgreSQL's RAISE EXCEPTION is not an IntegrityError: the two
                    # trigger messages are matched by their text
                    real = (isinstance(exc, IntegrityError) or "append-only" in str(exc)
                            or "(D28)" in str(exc))
                    results.append((name, real, type(exc).__name__ if real
                                    else f"wrong error, not a refusal: {exc}"[:300]))
            finally:
                tx.rollback()
    for name, probe in MUST_ALLOW:
        with engine.connect() as c:
            _sqlite_fk(c)
            tx = c.begin()
            try:
                probe(c, _setup(c))
                results.append((name, True, "allowed"))
            except Exception as exc:  # noqa: BLE001
                results.append((name, False, f"refused: {exc}"[:300]))
            finally:
                tx.rollback()
    return results
