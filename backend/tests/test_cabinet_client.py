"""The cabinet client's response handling (spec §2.5), against the simulator.

Replaces test_pedestal_client.py / test_pedestal_api.py, which tested the old
client's internals through mocks. Here every case is a real HTTP exchange with
the simulator built from the cabinet's code.
"""
import asyncio
from datetime import timedelta

import httpx
import pytest
from jose import jwt

from app.cabinet import client as cc
from app.cabinet.client import CabinetClient, cache_key
from simulator.cabinet_sim import create_app, make_state, session_payload


class Waits:
    def __init__(self):
        self.seen = []

    async def __call__(self, s):
        self.seen.append(s)


def _client(state=None, waits=None, **kw):
    state = state or make_state("full")
    c = CabinetClient(
        marina_id=1, base_url="http://cabinet.sim", service_email=state.service_email,
        service_password=state.service_password, erp_api_key=state.erp_api_key,
        transport=httpx.ASGITransport(app=create_app(state)), sleep=waits or Waits(), **kw)
    return c, state


def run(coro):
    return asyncio.run(coro)


def _logins(state):
    return len(state.tokens)


# ─── token ───────────────────────────────────────────────────────────────────

def test_token_is_reused():
    c, st = _client()
    run(c.health())
    run(c.list_berths())
    assert _logins(st) == 1


def test_expired_token_relogin_once_and_the_call_succeeds():
    """The cabinet's token lives 120 min. Before phase 2 the ERP cached it for 7 h
    and, on the 401, dropped it without retrying — serving stale data for ~5 h
    out of every 7."""
    c, st = _client()
    run(c.health())
    st.tokens = {k: v - timedelta(hours=3) for k, v in st.tokens.items()}   # expired
    out = run(c.health())
    assert out.code == "ok"
    assert _logins(st) == 2


def test_token_lifetime_comes_from_the_jwt_exp():
    c, _ = _client()
    from app.utils.time import utcnow
    exp = int((utcnow().replace(tzinfo=None) - __import__("datetime").datetime(1970, 1, 1))
              .total_seconds()) + 7200
    token = jwt.encode({"sub": "x", "exp": exp}, "k", algorithm="HS256")

    async def fake_post(*a, **kw):
        return httpx.Response(200, json={"access_token": token, "token_type": "bearer"})

    class H:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        post = staticmethod(fake_post)

    c._http = lambda: H()
    run(c._token_now())
    left = (c._token_expires - utcnow()).total_seconds()
    assert 7200 - 5 * 60 - 30 < left < 7200 - 5 * 60 + 30


def test_wrong_service_password_is_auth_failed_not_an_exception():
    c, st = _client()
    c._service_password = "wrong"
    assert run(c.health()).code == "cabinet_auth_failed"


# ─── 5xx / timeout: 3 attempts, waits 1 s and 2 s ────────────────────────────

def test_5xx_three_attempts_with_backoff_then_no_contact():
    waits = Waits()
    c, st = _client(waits=waits)
    st.fail_next = [500, 500, 500]
    out = run(c.health())
    assert out.code == "no_contact" and out.is_stale
    assert waits.seen == [1.0, 2.0]
    assert len([x for x in st.calls if x[1].endswith("/health")]) == 3


def test_5xx_then_recovery():
    c, st = _client()
    st.fail_next = [502]
    assert run(c.health()).code == "ok"


def test_connect_error_is_no_contact():
    c = CabinetClient(1, "http://127.0.0.1:1", "a", "b", sleep=Waits(), timeout=0.5)
    out = run(c.health())
    assert out.code == "no_contact"


# ─── stale cache, keyed by parameters (O20) ──────────────────────────────────

def test_cache_key_includes_query_parameters():
    a = cache_key("analytics.daily", "/api/ext/analytics/consumption/daily",
                  {"date_from": "2026-10-01", "date_to": "2026-10-07"})
    b = cache_key("analytics.daily", "/api/ext/analytics/consumption/daily",
                  {"date_from": "2026-09-01", "date_to": "2026-09-07"})
    assert a != b


def test_stale_fallback_never_returns_another_ranges_data(client, sim, setup_test_database):
    """O20: before phase 2 every date range shared one cache row."""
    from tests.conftest import TestSession
    st = sim.state.sim
    db = TestSession()
    try:
        c, _ = _client(st)
        assert run(c.daily_analytics(db, "2026-10-01", "2026-10-07")).code == "ok"
        st.fail_next = [500] * 10
        other = run(c.daily_analytics(db, "2026-09-01", "2026-09-07"))
        assert other.code == "no_contact" and other.data is None
        st.fail_next = [500] * 10
        same = run(c.daily_analytics(db, "2026-10-01", "2026-10-07"))
        assert same.code == "stale" and same.synced_at is not None
    finally:
        db.close()


# ─── 403 / 503 / 409 / 422 / 404 ─────────────────────────────────────────────

def test_403_not_enabled_is_remembered_for_an_hour(monkeypatch):
    c, st = _client()
    del st.enabled["sessions.active"]
    assert run(c.active_sessions()).code == "not_enabled"
    assert run(c.active_sessions()).code == "not_enabled"
    assert len([x for x in st.calls if x[1].endswith("/sessions/active")]) == 1
    from app.utils.time import utcnow
    later = utcnow() + timedelta(hours=1, minutes=1)
    monkeypatch.setattr(cc, "utcnow", lambda: later)
    st.enabled["sessions.active"] = "monitor"
    c._token = None
    assert run(c.active_sessions()).code == "ok"


def test_409_session_state_changed_is_a_400_on_the_cabinet():
    c, st = _client()
    st.sessions = [{"id": 7, "pedestal_id": 1, "socket_id": 1, "type": "electricity",
                    "status": "active", "started_at": None, "ended_at": None,
                    "energy_kwh": None, "water_liters": None, "customer_id": None,
                    "nfc_user_id": None, "deny_reason": None, "customer_name": None}]
    assert run(c.allow_session(7)).code == "session_state_changed"
    assert run(c.allow_session(8)).code == "not_found"


def test_bad_outlet_name_is_refused_before_sending():
    c, st = _client()
    assert run(c.socket_cmd(1, "1", "activate")).code == "erp_bug"
    assert not [x for x in st.calls if x[1].endswith("/cmd")]


def test_water_command_goes_to_the_valve_route():
    c, st = _client()
    out = run(c.socket_cmd(1, "V1", "stop"))
    assert out.ok and out.data["valve"] == "V1"


# ─── channel B ───────────────────────────────────────────────────────────────

def test_channel_b_uses_the_api_key_and_never_a_bearer():
    st = make_state("full")
    seen = {}

    async def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, json=session_payload())

    c = CabinetClient(1, "http://cabinet.sim", "a", "b", erp_api_key="k",
                      transport=httpx.MockTransport(handler), sleep=Waits())
    run(c.nfc_session_for_reconciliation(101))
    assert seen.get("x-api-key") == "k" and "authorization" not in seen
    del st


def test_channel_b_wrong_key_is_auth_failed():
    c, st = _client()
    c._erp_api_key = "nope"
    assert run(c.nfc_stop(1)).code == "cabinet_auth_failed"


def test_channel_b_without_a_key_is_unavailable_not_a_crash():
    c, _ = _client()
    c._erp_api_key = None
    assert run(c.nfc_scan("t", "u")).code == "capability_unavailable"


def test_stop_after_staff_ended_it_is_already_ended_not_an_error():
    c, st = _client()
    st.nfc_sessions[9] = session_payload(session_id=9, status="ended")
    out = run(c.nfc_stop(9))
    assert out.code == "already_ended"
    from app.cabinet.outcomes import NOT_ERRORS
    assert out.code in NOT_ERRORS


def test_reconciliation_reads_mark_the_cabinet_and_say_so_in_their_names():
    c, st = _client()
    st.nfc_sessions[9] = session_payload(session_id=9, customer_id="u1")
    run(c.nfc_session_for_reconciliation(9))
    run(c.nfc_sessions_by_user_for_reconciliation("u1"))
    assert st.reconciled[9] == 2


@pytest.mark.parametrize("name", ["nfc_session", "nfc_sessions_by_user"])
def test_no_display_friendly_alias_exists(name):
    assert not hasattr(CabinetClient, name)


# ── O61: a client per call must not rebuild TLS on the event loop ─────────────

def test_o61_every_cabinet_call_shares_one_tls_context(monkeypatch):
    # httpx re-reads the CA bundle for each new client (~0.24 s of CPU on the
    # event loop); a berths request makes ~10 calls, so that alone took it past
    # the browser's 10 s on a busy machine (spec §11 O61)
    seen = []
    real = httpx.AsyncClient

    def spy(*a, **kw):
        seen.append(kw.get("verify"))
        return real(*a, **kw)

    monkeypatch.setattr(cc.httpx, "AsyncClient", spy)
    c, _ = _client()
    run(c.health())
    run(c.list_berths())
    assert len(seen) >= 3                      # token + two calls
    assert all(v is cc.TLS for v in seen)


def test_o61_no_http_client_in_the_app_builds_its_own_tls():
    import re
    from pathlib import Path
    app = Path(cc.__file__).resolve().parents[1]
    bad = [f"{f.relative_to(app)}:{n}"
           for f in app.rglob("*.py")
           for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1)
           if re.search(r"httpx\.(Async)?Client\(", line) and "verify=TLS" not in line]
    assert bad == []
