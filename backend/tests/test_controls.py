"""
test_controls.py — session and outlet controls, with audit, against the simulator.

Verifies:
- allow/deny/stop/outlet commands log user, marina, pedestal, action AND the
  cabinet's outcome code to audit_log — including refused commands
- marina_manager blocked from controlling sessions in other marinas
- (since phase 2) no mocks of the cabinet client: the real client talks to the
  simulator, so the request the ERP sends is the request the cabinet would get
"""
import pytest

from app.utils.time import utcnow


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


@pytest.mark.parametrize("action,status", [("allow", "pending"), ("deny", "pending"),
                                           ("stop", "active")])
def test_session_command_logs_audit_with_outcome(client, admin_headers, marina_id, sim,
                                                 action, status):
    sim.state.sim.sessions = [_session(41, status)]
    kw = {"json": {"reason": "No capacity"}} if action == "deny" else {}
    r = client.post(f"/api/marinas/{marina_id}/sessions/41/{action}",
                    headers=admin_headers, params={"pedestal_id": 1}, **kw)
    assert r.status_code == 200, r.text
    assert r.json()["outcome"]["code"] == "ok"
    entry = _audit(marina_id, f"{action}_session", 41)
    assert entry is not None and entry.pedestal_id == 1 and entry.performed_at is not None
    assert entry.details["outcome"] == "ok"
    if action == "deny":
        assert entry.details["reason"] == "No capacity"


def test_refused_command_is_audited_too(client, admin_headers, marina_id, sim):
    sim.state.sim.sessions = [_session(42, "active")]
    r = client.post(f"/api/marinas/{marina_id}/sessions/42/allow", headers=admin_headers)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "session_state_changed"
    assert _audit(marina_id, "allow_session", 42).details["outcome"] == "session_state_changed"


def test_outlet_command_reaches_the_cabinet_by_real_name(client, admin_headers, marina_id, sim):
    r = client.post(f"/api/marinas/{marina_id}/pedestals/1/outlets/Q3/cmd",
                    json={"action": "activate"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert ("POST", "/api/ext/controls/pedestal/1/socket/Q3/cmd") in sim.state.sim.calls
    assert _audit(marina_id, "outlet_activate").details["outlet"] == "Q3"


def test_outlet_command_rejects_unknown_actions(client, admin_headers, marina_id, sim):
    r = client.post(f"/api/marinas/{marina_id}/pedestals/1/outlets/Q3/cmd",
                    json={"action": "maintenance"}, headers=admin_headers)
    assert r.status_code == 422          # ERP validation; never sent to the cabinet
    assert not [c for c in sim.state.sim.calls if c[1].endswith("/cmd")]


def test_marina_manager_blocked_from_restricted_marina_controls(
    client, manager_headers, restricted_marina_id, sim
):
    r = client.post(f"/api/marinas/{restricted_marina_id}/sessions/1/allow",
                    headers=manager_headers)
    assert r.status_code == 403
    assert sim.state.sim.calls == []


def test_marina_manager_can_control_own_marina(client, manager_headers, marina_id, sim):
    sim.state.sim.sessions = [_session(10, "pending")]
    r = client.post(f"/api/marinas/{marina_id}/sessions/10/allow", headers=manager_headers)
    assert r.status_code == 200


def test_unauthenticated_controls_return_401(client, marina_id):
    r = client.post(f"/api/marinas/{marina_id}/sessions/1/allow")
    assert r.status_code == 401
