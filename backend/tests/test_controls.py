"""
test_controls.py — session and outlet controls, with audit, against the simulator.

Verifies:
- allow/deny/stop/outlet commands log user, marina, pedestal, action AND the
  cabinet's outcome code to audit_log — including refused commands
- (phase 4) EVERY command is a command_audit row written BEFORE the call and
  completed with the outcome: full URL, operator, reason, tag_source (§4.7, §5.3)
- (phase 4) no reason -> 422, nothing sent, nothing written; no cabinet in the
  ERP -> 409, nothing sent
- marina_manager blocked from controlling sessions in other marinas
- (since phase 2) no mocks of the cabinet client: the real client talks to the
  simulator, so the request the ERP sends is the request the cabinet would get
"""
import pytest

from app.utils.time import utcnow

MAP = {"1": ["Q1"], "2": ["Q2"], "3": ["Q3", "V1"], "4": ["Q4", "V1"]}
WHY = {"reason": "gost na vezu 3 zove recepciju"}


@pytest.fixture
def cabinet(cabinet_config, marina_id):
    return cabinet_config(marina_id, "full", MAP)


def _session(sid, status):
    return {"id": sid, "pedestal_id": 1, "socket_id": 1, "type": "electricity",
            "status": status, "started_at": utcnow().isoformat(), "ended_at": None,
            "energy_kwh": None, "water_liters": None, "customer_id": None,
            "nfc_user_id": None, "deny_reason": None, "customer_name": None}


def _audit(marina_id, action, target_id=None):
    from tests.conftest import TestSession
    from app.models.cache import AuditLog
    from app.models.user import User

    db = TestSession()
    try:
        user = db.query(User).filter(User.email == "superadmin@test.erp").first()
        q = db.query(AuditLog).filter(AuditLog.marina_id == marina_id,
                                      AuditLog.action == action, AuditLog.user_id == user.id)
        if target_id is not None:
            q = q.filter(AuditLog.target_id == target_id)
        return q.order_by(AuditLog.id.desc()).first()
    finally:
        db.close()


def _command_rows(cabinet_id):
    from tests.conftest import TestSession
    from app.models.metering import CommandAudit

    db = TestSession()
    try:
        return (db.query(CommandAudit).filter(CommandAudit.cabinet_id == cabinet_id)
                .order_by(CommandAudit.id).all())
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _clean_command_audit():
    _wipe()
    yield
    _wipe()


def _wipe():
    from tests.conftest import TestSession
    from app.models.metering import CommandAudit
    db = TestSession()
    try:
        db.query(CommandAudit).delete()
        db.commit()
    finally:
        db.close()


@pytest.mark.parametrize("action,status", [("allow", "pending"), ("deny", "pending"),
                                           ("stop", "active")])
def test_session_command_logs_audit_with_outcome(client, admin_headers, marina_id, sim, cabinet,
                                                 action, status):
    sim.state.sim.sessions = [_session(41, status)]
    r = client.post(f"/api/marinas/{marina_id}/sessions/41/{action}",
                    headers=admin_headers, params={"pedestal_id": 1}, json=WHY)
    assert r.status_code == 200, r.text
    assert r.json()["outcome"]["code"] == "ok"
    entry = _audit(marina_id, f"{action}_session", 41)
    assert entry is not None and entry.pedestal_id == 1 and entry.performed_at is not None
    assert entry.details["outcome"] == "ok"
    assert entry.details["reason"] == WHY["reason"]
    [row] = _command_rows(cabinet)
    assert (row.endpoint_key, row.action, row.actor_type, row.actor_ref) == (
        f"controls.{action}", action, "operator", "superadmin@test.erp")
    assert row.reason == WHY["reason"] and row.outcome == "ok" and row.completed_at
    assert row.request_url == f"http://pedestal-sw.test/api/ext/controls/41/{action}"


def test_refused_command_is_audited_too(client, admin_headers, marina_id, sim, cabinet):
    sim.state.sim.sessions = [_session(42, "active")]
    r = client.post(f"/api/marinas/{marina_id}/sessions/42/allow", headers=admin_headers,
                    json=WHY)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "session_state_changed"
    assert _audit(marina_id, "allow_session", 42).details["outcome"] == "session_state_changed"
    [row] = _command_rows(cabinet)
    assert (row.outcome, row.http_status) == ("session_state_changed", 400)
    assert row.detail == "Session is active, expected pending"   # the cabinet's own words


def test_outlet_command_reaches_the_cabinet_by_real_name(client, admin_headers, marina_id, sim,
                                                         cabinet):
    r = client.post(f"/api/marinas/{marina_id}/pedestals/1/outlets/Q3/cmd",
                    json={"action": "activate", **WHY}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert ("POST", "/api/ext/controls/pedestal/1/socket/Q3/cmd") in sim.state.sim.calls
    assert _audit(marina_id, "outlet_activate").details["outlet"] == "Q3"
    [row] = _command_rows(cabinet)
    assert row.request_url.endswith("/api/ext/controls/pedestal/1/socket/Q3/cmd")
    assert row.outlet_id is not None and row.tag_source is None   # Q3 has no tag yet


def test_manual_activate_sends_the_mapped_tag_and_says_so(client, admin_headers, marina_id, sim,
                                                         cabinet):
    """§5.3 (a): the ERP sends the tag from ITS mapping; the audit says 'mapping', never
    'scan' — otherwise the record would claim the guest was there."""
    r = client.post(f"/api/marinas/{marina_id}/cabinets/{cabinet}/nfc-tags/import",
                    headers={**admin_headers, "Content-Type": "text/csv"},
                    content="outlet,uid\nQ2,04A1B2C3D4E5F6\n")
    assert r.status_code == 200, r.text
    r = client.post(f"/api/marinas/{marina_id}/pedestals/1/outlets/Q2/cmd",
                    json={"action": "activate", **WHY}, headers=admin_headers)
    assert r.status_code == 200, r.text
    [row] = _command_rows(cabinet)
    assert row.tag_source == "mapping"


def test_command_without_reason_is_never_sent_nor_written(client, admin_headers, marina_id,
                                                          sim, cabinet):
    for url, body in ((f"/api/marinas/{marina_id}/pedestals/1/outlets/Q3/cmd",
                       {"action": "activate"}),
                      (f"/api/marinas/{marina_id}/pedestals/1/outlets/Q3/cmd",
                       {"action": "activate", "reason": "  "}),
                      (f"/api/marinas/{marina_id}/sessions/41/stop", {})):
        r = client.post(url, json=body, headers=admin_headers)
        assert r.status_code == 422, (url, body, r.text)
    assert not [c for c in sim.state.sim.calls if c[0] == "POST"]
    assert _command_rows(cabinet) == []


def test_row_is_written_before_the_call(client, admin_headers, marina_id, sim, cabinet):
    """A command that never got an answer stays visible: the row exists while the
    call is in flight, with outcome NULL (§5.3)."""
    seen = []                       # what the audit table held at EACH call to the cabinet
    import simulator.cabinet_sim as cs
    original = cs._internal

    def spy(key, p, body, s):
        seen.append([(r.endpoint_key, r.outcome) for r in _command_rows(cabinet)])
        return original(key, p, body, s)

    cs._internal = spy
    try:
        r = client.post(f"/api/marinas/{marina_id}/pedestals/1/outlets/Q1/cmd",
                        json={"action": "stop", **WHY}, headers=admin_headers)
    finally:
        cs._internal = original
    assert r.status_code == 200, r.text
    assert seen == [[("controls.socket_cmd", None)]], "sent before the row, or sent twice"
    assert [(r.endpoint_key, r.outcome) for r in _command_rows(cabinet)] == [
        ("controls.socket_cmd", "ok")]


def test_no_cabinet_in_the_erp_no_command(client, admin_headers, marina_id, sim):
    """Nothing to write the audit row against -> nothing is sent."""
    from tests.conftest import _clear_cabinets
    _clear_cabinets(marina_id)
    r = client.post(f"/api/marinas/{marina_id}/pedestals/1/outlets/Q1/cmd",
                    json={"action": "activate", **WHY}, headers=admin_headers)
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "cabinet_not_configured")
    assert not [c for c in sim.state.sim.calls if c[0] == "POST"]


def test_outlet_command_rejects_unknown_actions(client, admin_headers, marina_id, sim, cabinet):
    r = client.post(f"/api/marinas/{marina_id}/pedestals/1/outlets/Q3/cmd",
                    json={"action": "maintenance", **WHY}, headers=admin_headers)
    assert r.status_code == 422          # ERP validation; never sent to the cabinet
    assert not [c for c in sim.state.sim.calls if c[1].endswith("/cmd")]


def test_marina_manager_blocked_from_restricted_marina_controls(
    client, manager_headers, restricted_marina_id, sim
):
    r = client.post(f"/api/marinas/{restricted_marina_id}/sessions/1/allow",
                    headers=manager_headers, json=WHY)
    assert r.status_code == 403
    assert sim.state.sim.calls == []


def test_marina_manager_can_control_own_marina(client, manager_headers, marina_id, sim, cabinet):
    sim.state.sim.sessions = [_session(10, "pending")]
    r = client.post(f"/api/marinas/{marina_id}/sessions/10/allow", headers=manager_headers,
                    json=WHY)
    assert r.status_code == 200


def test_unauthenticated_controls_return_401(client, marina_id):
    r = client.post(f"/api/marinas/{marina_id}/sessions/1/allow", json=WHY)
    assert r.status_code == 401
