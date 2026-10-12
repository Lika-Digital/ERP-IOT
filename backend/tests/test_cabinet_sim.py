"""TC-ERP-SIM-00 … SIM-16 — the ERP against the cabinet simulator (spec §9.1).

The real ERP app, the real cabinet client, and the simulator built from the
cabinet's code (simulator/cabinet_sim.py). No mocks of the client.

Phase-2 scope note, per test where it applies: billing_records (phase 7), the
mapping tables (phase 3) and the NFC flow (phase 7) do not exist yet. Where a
SIM test names them, this file tests the contract-level part that phase 2
builds, and says so.
"""
import asyncio
import json
import re
from pathlib import Path

import httpx
import pytest

from app.cabinet import contract
from app.cabinet.berth_view import parse_occupancy
from app.cabinet.client import CabinetClient
from app.cabinet.session_payload import CONTRACT_KEYS, PayloadError, parse_session
from simulator.cabinet_sim import create_app, make_state, session_payload

_REPO = Path(__file__).resolve().parents[2]


def _state(sim):
    return sim.state.sim


def _switch(sim, profile):
    """Change the simulator profile, keeping the seeded marina's credentials."""
    old = _state(sim)
    new = make_state(profile)
    new.service_email, new.service_password = old.service_email, old.service_password
    sim.state.sim = new
    return new


def _berths(client, admin_headers, marina_id):
    r = client.get(f"/api/marinas/{marina_id}/berths", headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


FULL_MAP = {"1": ["Q1"], "2": ["Q2"], "3": ["Q3", "V1"], "4": ["Q4", "V1"]}


def _nfc_client(state):
    return CabinetClient(
        marina_id=1, base_url="http://cabinet.sim", service_email=state.service_email,
        service_password=state.service_password, erp_api_key=state.erp_api_key,
        transport=httpx.ASGITransport(app=create_app(state)),
        sleep=lambda _s: asyncio.sleep(0),
    )


# ─── SIM-00  the simulator answers the contract ──────────────────────────────

def test_sim_00_session_payload_is_exactly_the_16_contract_keys():
    assert set(session_payload()) == CONTRACT_KEYS


def test_sim_00_three_occupancy_shapes_are_all_understood():
    st = make_state("full")
    st.berths[1]["last_analyzed"] = None
    c = _nfc_client(st)
    body = asyncio.run(c.berth_occupancy("MAR_KRK_ORM_01")).data
    rows = {r["berth_id"]: r for r in parse_occupancy(body)}
    assert rows[1]["occupied"] is True and rows[1]["last_analyzed"]        # shape C
    assert rows[2]["occupied"] is None and rows[2]["note"]                 # shape B
    st.berths = []
    body = asyncio.run(c.berth_occupancy("MAR_KRK_ORM_01")).data
    assert parse_occupancy(body) == [] and "message" in body               # shape A


# ─── SIM-00c / 00d / 00e / 11 / 12 / 13 — the session payload, via channel B ─

def _fetch_session(**over):
    st = make_state("full")
    p = session_payload(**over)
    st.nfc_sessions[p["session_id"]] = p
    raw = asyncio.run(_nfc_client(st).nfc_session_for_reconciliation(p["session_id"]))
    assert raw.ok, raw
    return raw.data


@pytest.mark.parametrize("price_key", ["estimated_cost", "cost", "price", "amount"])
def test_sim_00c_price_from_the_cabinet_does_not_exist_after_parsing(price_key):
    parsed = parse_session(_fetch_session(**{price_key: 12.34})).to_dict()
    assert price_key not in set(_keys(parsed))
    assert "12.34" not in json.dumps(parsed)


def test_sim_00d_and_13_water_on_v1_is_never_attributed_to_q1():
    p = parse_session(_fetch_session(
        socket_id="V1", session_type="water", energy_kwh=None, water_liters=40.0,
        meter_energy_start_kwh=None, meter_energy_end_kwh=None,
        meter_water_start_l=500.0, meter_water_end_l=540.0))
    assert p.outlet_name == "V1" and p.unit == "L"


def test_sim_13_a_bare_socket_number_is_refused():
    with pytest.raises(PayloadError):
        parse_session(_fetch_session(socket_id=1))


def test_sim_00e_and_12_recompute_mismatch_goes_to_review_never_billable():
    # phase 2: billing_records does not exist yet; "never billing" is `billable` False
    p = parse_session(_fetch_session(energy_kwh=4.0))   # registers say 3.25
    assert p.manual_review and not p.billable
    assert "recompute_mismatch" in {f.code for f in p.findings}


def test_sim_11_null_is_not_zero():
    p = parse_session(_fetch_session(energy_kwh=None, meter_energy_end_kwh=None,
                                     consumption_source="unknown"))
    assert p.consumption is None          # rendered as —, never 0
    assert p.manual_review and not p.billable


# ─── SIM-00g  by-user (and /session/{id}) are never called for display ───────

def test_sim_00g_state_changing_nfc_reads_are_only_reachable_from_reconciliation():
    """Both GET /api/nfc/session/{id} and /sessions/by-user write last_reconciled_at
    on the cabinet (nfc.py:688-759). Only a reconciliation module may call them."""
    app_dir = _REPO / "backend" / "app"
    offenders = []
    for f in app_dir.rglob("*.py"):
        rel = f.relative_to(app_dir).as_posix()
        # the client defines them; the reconciler (phase 4) is the one module that calls them
        if rel in ("cabinet/client.py", "services/reconciler.py") or "__pycache__" in rel:
            continue
        if "_for_reconciliation" in f.read_text(encoding="utf-8"):
            offenders.append(rel)
    assert offenders == []


def test_sim_00g_screens_do_not_touch_channel_b(client, admin_headers, marina_id, sim):
    _berths(client, admin_headers, marina_id)
    client.get(f"/api/marinas/{marina_id}/dashboard", headers=admin_headers)
    assert not [c for c in _state(sim).calls if c[1].startswith("/api/nfc/")]
    assert _state(sim).reconciled == {}


# ─── SIM-01  full cabinet 4+2 ────────────────────────────────────────────────

def test_sim_01_full_cabinet(client, admin_headers, marina_id, sim, cabinet_config):
    cabinet_config(marina_id, "full", FULL_MAP)
    v = _berths(client, admin_headers, marina_id)
    names = {o["name"] for b in v["berths"] for o in b["outlets"]}
    assert names == {"Q1", "Q2", "Q3", "Q4", "V1"}
    assert v["cabinet"]["device_type"] == "full"
    b1 = next(b for b in v["berths"] if b["berth_id"] == 1)
    assert b1["pedestal"] == {"pk": 1, "display_id": "MAR_KRK_ORM_01"}


# ─── SIM-02  retrofit: water is drawn nowhere ────────────────────────────────

def test_sim_02_retrofit_has_no_water_anywhere(client, admin_headers, marina_id, sim,
                                               cabinet_config):
    _switch(sim, "retrofit")
    cabinet_config(marina_id, "retrofit", {"1": ["Q1"], "2": ["Q2"], "3": ["Q3"], "4": ["Q4"]})
    v = _berths(client, admin_headers, marina_id)
    text = json.dumps(v)
    assert '"water"' not in text and "V1" not in text and "V2" not in text
    # the cabinet itself still lists two valves — the ERP must not believe it
    assert any(c[1].endswith("/load") for c in _state(sim).calls)


def test_sim_02_unconfigured_cabinet_guesses_nothing(client, admin_headers, marina_id, sim):
    # no cabinets row for the marina (phase 3: the source is the database)
    v = _berths(client, admin_headers, marina_id)
    assert v["cabinet"]["configured"] is False
    assert all(b["outlets"] == [] for b in v["berths"])
    assert all(b["signals"]["power"] == "UNKNOWN" for b in v["berths"])


# ─── SIM-03  three-phase Q1 ──────────────────────────────────────────────────

def test_sim_03_three_phase_q1_one_phase_q2(client, admin_headers, marina_id, sim,
                                            cabinet_config):
    cabinet_config(marina_id, "full", FULL_MAP)
    outlets = {o["name"]: o for b in _berths(client, admin_headers, marina_id)["berths"]
               for o in b["outlets"]}
    assert outlets["Q1"]["phases"] == 3 and len(outlets["Q1"]["current_amps"]) == 3
    assert outlets["Q2"]["phases"] == 1 and len(outlets["Q2"]["current_amps"]) == 1


# ─── SIM-04  shared valve ────────────────────────────────────────────────────

def test_sim_04_shared_valve_is_a_supervision_note_only(client, admin_headers, marina_id, sim,
                                                        cabinet_config):
    # phase 2: no billing exists; the clarification lives only on the outlet view
    cabinet_config(marina_id, "full", FULL_MAP)
    v = _berths(client, admin_headers, marina_id)
    by_id = {b["berth_id"]: b for b in v["berths"]}
    v1_on_3 = next(o for o in by_id[3]["outlets"] if o["name"] == "V1")
    v1_on_4 = next(o for o in by_id[4]["outlets"] if o["name"] == "V1")
    assert v1_on_3["shared_with_berths"] == [4] and v1_on_4["shared_with_berths"] == [3]
    assert "shared_with_berths" not in json.dumps(by_id[3]["status_sentence"])


# ─── SIM-05  silent cabinet; stale data travels to the colour ────────────────

def test_sim_05_silent_cabinet_is_grey_although_it_looks_connected(
        client, admin_headers, marina_id, sim, cabinet_config):
    _switch(sim, "silent")
    cabinet_config(marina_id, "full", FULL_MAP)
    v = _berths(client, admin_headers, marina_id)
    assert {b["status_code"] for b in v["berths"]} == {"no_contact"}
    assert {b["berth_colour"] for b in v["berths"]} == {"grey"}
    assert all("controls" not in o for b in v["berths"] for o in b["outlets"])


def test_sim_05_stale_cache_is_grey_with_time(client, admin_headers, marina_id, sim,
                                              cabinet_config):
    cabinet_config(marina_id, "full", FULL_MAP)
    _berths(client, admin_headers, marina_id)                 # fills the cache
    _state(sim).fail_next = [500] * 200                       # now the cabinet is down
    v = _berths(client, admin_headers, marina_id)
    assert v["is_stale"] is True
    assert {b["berth_colour"] for b in v["berths"]} == {"grey"}
    assert all(b["data_as_of"] for b in v["berths"])
    assert all("controls" not in o for b in v["berths"] for o in b["outlets"])


# ─── SIM-06  Smart Mode OFF ──────────────────────────────────────────────────

def test_sim_06_smart_mode_off_reads_render_controls_absent(
        client, admin_headers, marina_id, sim, cabinet_config):
    _switch(sim, "smart_off")
    cabinet_config(marina_id, "full", FULL_MAP)
    v = _berths(client, admin_headers, marina_id)
    assert {b["status_code"] for b in v["berths"]} == {"standalone"}
    outlets = [o for b in v["berths"] for o in b["outlets"]]
    assert outlets and all("power_kw" in o for o in outlets if o["medium"] == "electricity")
    assert all("controls" not in o for o in outlets)


def test_sim_06_and_07_smart_mode_409_is_a_sentence_never_500(client, admin_headers,
                                                              marina_id, sim, cabinet_config):
    cabinet_config(marina_id, "full", FULL_MAP)
    _switch(sim, "smart_off")
    r = client.post(f"/api/marinas/{marina_id}/pedestals/1/outlets/Q2/cmd",
                    json={"action": "activate", "reason": "provjera"}, headers=admin_headers)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "standalone"
    assert r.json()["detail"]["sentence"]


# ─── SIM-07  three different 409s ────────────────────────────────────────────

def test_sim_07_no_plug_is_its_own_code(client, admin_headers, marina_id, sim, cabinet_config):
    cabinet_config(marina_id, "full", FULL_MAP)
    _state(sim).sockets[1].plug_inserted = False
    r = client.post(f"/api/marinas/{marina_id}/pedestals/1/outlets/Q2/cmd",
                    json={"action": "activate", "reason": "provjera"}, headers=admin_headers)
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "awaiting_plug")


def test_sim_07_outlet_busy_is_its_own_code():
    # On the cabinet "already in use" exists only on NFC scan (nfc.py), not on socket_cmd.
    st = make_state("full")
    st.nfc_sessions[5] = session_payload(session_id=5, socket_id="Q1", status="active",
                                         energy_kwh=None, meter_energy_end_kwh=None,
                                         consumption_source=None)
    out = asyncio.run(_nfc_client(st)._nfc("POST", contract.NFC_SCAN, "nfc.scan",
                                           body={"nfc_tag_id": "t", "user_id": "u",
                                                 "_outlet": "Q1"}))
    assert out.code == "outlet_busy"


def test_sim_07_three_409s_three_codes_three_sentences():
    from app.cabinet.outcomes import SENTENCES, classify_409
    from simulator.cabinet_sim import SMART_MODE_GW_409
    codes = [classify_409(SMART_MODE_GW_409), classify_409("Socket has no plug inserted"),
             classify_409("This socket is already in use. Please use another socket.")]
    assert codes == ["standalone", "awaiting_plug", "outlet_busy"]
    assert len({SENTENCES[c] for c in codes}) == 3


# ─── SIM-08  403 is not an error ─────────────────────────────────────────────

def test_sim_08_not_enabled_stops_calling_and_removes_controls(
        client, admin_headers, marina_id, sim, cabinet_config):
    cabinet_config(marina_id, "full", FULL_MAP)
    del _state(sim).enabled["controls.socket_cmd"]
    url = f"/api/marinas/{marina_id}/pedestals/1/outlets/Q2/cmd"
    r1 = client.post(url, json={"action": "activate", "reason": "provjera"}, headers=admin_headers)
    assert (r1.status_code, r1.json()["detail"]["code"]) == (503, "not_enabled")
    n = len([c for c in _state(sim).calls if c[1].endswith("/cmd")])
    r2 = client.post(url, json={"action": "activate", "reason": "provjera"}, headers=admin_headers)
    assert r2.json()["detail"]["code"] == "not_enabled"
    assert len([c for c in _state(sim).calls if c[1].endswith("/cmd")]) == n, "called again"
    v = _berths(client, admin_headers, marina_id)
    assert all("controls" not in o for b in v["berths"] for o in b["outlets"])


def test_sim_08_direct_route_not_enabled_is_503_without_detail_and_same_code():
    st = make_state("full")
    del st.enabled["load.pedestal_get_ext"]
    out = asyncio.run(_nfc_client(st).pedestal_load(1))
    assert (out.code, out.http_status) == ("not_enabled", 503)


# ─── SIM-09  422 is an ERP bug ───────────────────────────────────────────────

def test_sim_09_display_id_on_pk_route_is_never_sent():
    st = make_state("full")
    out = asyncio.run(_nfc_client(st).call("load.pedestal_get_ext",
                                           path_params={"pedestal_id": "MAR_KRK_ORM_01"}))
    assert out.code == "erp_bug"
    assert not [c for c in st.calls if c[1].endswith("/load")]


def test_sim_09_a_422_from_the_cabinet_is_logged_and_not_retried(monkeypatch, caplog):
    st = make_state("full")
    ep = contract.ENDPOINTS["load.pedestal_get_ext"]
    monkeypatch.setitem(contract.ENDPOINTS, "load.pedestal_get_ext",
                        contract.Endpoint(ep.key, ep.method, ep.catalog_path,
                                          contract.IdType.PK_OR_DISPLAY, ep.mode, ep.used_for))
    out = asyncio.run(_nfc_client(st).call("load.pedestal_get_ext",
                                           path_params={"pedestal_id": "MAR_KRK_ORM_01"}))
    assert (out.code, out.http_status) == ("erp_bug", 422)
    assert len([c for c in st.calls if c[1].endswith("/load")]) == 1
    assert "ERP BUG" in caplog.text


# ─── SIM-10  doubled ext ─────────────────────────────────────────────────────

def test_sim_10_doubled_ext_is_refused_before_sending():
    for ep in contract.ENDPOINTS.values():
        assert "/api/ext/ext/" not in ep.path


def test_sim_10_doubled_ext_401_logs_the_full_url(monkeypatch, caplog):
    st = make_state("full")
    real = contract.build_path
    monkeypatch.setattr(contract, "build_path",
                        lambda k, **p: real(k, **p).replace("/api/ext/", "/api/ext/ext/"))
    out = asyncio.run(_nfc_client(st).pedestal_status(1))
    assert out.code == "cabinet_auth_failed"
    assert "http://cabinet.sim/api/ext/ext/pedestals/1/status" in caplog.text


# ─── SIM-14  both UID forms ──────────────────────────────────────────────────

def test_sim_14_krk_tag_found_by_both_forms():
    # D6.1 example tag; phase 3 stores both columns, phase 2 owns the lookup rule
    from app.cabinet.nfc_uid import both_forms, find_tag

    class T:
        uid_primary, uid_reversed = both_forms("35:B2:5A:04:09:01:04:E0")
        outlet = "Q1"

    assert find_tag("35:B2:5A:04:09:01:04:E0", [T]).outlet == "Q1"
    assert find_tag("E0:04:01:09:04:5A:B2:35", [T]).outlet == "Q1"


# ─── SIM-15  statuses are computed on the server only ────────────────────────

def test_sim_15_no_status_code_is_derived_in_the_frontend():
    from app.cabinet.berth_status import STATUS_CODES
    src = _REPO / "frontend" / "src"
    offenders = []
    for f in list(src.rglob("*.ts")) + list(src.rglob("*.tsx")):
        text = f.read_text(encoding="utf-8")
        for code in STATUS_CODES:
            if re.search(rf"""['"`]{code}['"`]""", text):
                offenders.append(f"{f.relative_to(src)}: {code}")
    assert offenders == []


# ─── SIM-16  an absent capability renders no control ─────────────────────────

def test_sim_16_socket_the_cabinet_does_not_report_is_absent(
        client, admin_headers, marina_id, sim, cabinet_config):
    cabinet_config(marina_id, "full", FULL_MAP)
    _state(sim).sockets = [s for s in _state(sim).sockets if s.socket_id != 2]
    v = _berths(client, admin_headers, marina_id)
    b2 = next(b for b in v["berths"] if b["berth_id"] == 2)
    assert b2["outlets"] == []


# ─── §2.5 — no cabinet outcome ever becomes an ERP 500 ───────────────────────

@pytest.mark.parametrize("fault", ["smart_off", "no_plug", "disabled", "down", "unknown_session"])
def test_no_cabinet_outcome_is_an_erp_500(client, admin_headers, marina_id, sim, fault,
                                         cabinet_config):
    cabinet_config(marina_id, "full", FULL_MAP)
    st = _state(sim)
    if fault == "smart_off":
        st.smart_mode = False
    elif fault == "no_plug":
        st.sockets[0].plug_inserted = False
    elif fault == "disabled":
        st.enabled.clear()
    elif fault == "down":
        st.fail_next = [500] * 50
    urls = [
        ("post", f"/api/marinas/{marina_id}/pedestals/1/outlets/Q1/cmd",
         {"action": "activate", "reason": "provjera"}),
        ("post", f"/api/marinas/{marina_id}/sessions/999/allow", {"reason": "provjera"}),
        ("post", f"/api/marinas/{marina_id}/sessions/999/stop", {"reason": "provjera"}),
        ("get", f"/api/marinas/{marina_id}/berths", None),
        ("get", f"/api/marinas/{marina_id}/dashboard", None),
        ("get", f"/api/marinas/{marina_id}/energy/daily", None),
    ]
    for method, url, body in urls:
        r = getattr(client, method)(url, headers=admin_headers,
                                    **({"json": body} if body else {}))
        assert r.status_code < 500 or r.status_code in (502, 503), (url, r.status_code, r.text)
        if r.status_code >= 400:
            assert r.json()["detail"]["code"], (url, r.text)
