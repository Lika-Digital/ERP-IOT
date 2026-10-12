"""
test_alarms.py — Alarm log and acknowledgment tests.

Verifies:
- acknowledge_alarm writes audit_log entry with user_id + timestamp
- alarm_log is filtered by marina_id
- marina_manager blocked from other marinas
"""
from app.utils.time import utcnow


def _seed_alarm(marina_id: int, pedestal_id: int = 1) -> int:
    from tests.conftest import TestSession
    from app.models.cache import AlarmLog

    db = TestSession()
    try:
        entry = AlarmLog(
            marina_id=marina_id,
            pedestal_id=pedestal_id,
            alarm_data={"id": 100, "alarm_type": "temperature", "value": 60.0},
            received_at=utcnow(),
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry.id
    finally:
        db.close()


def test_alarm_log_returns_entries_for_marina(client, admin_headers, marina_id):
    _seed_alarm(marina_id)
    r = client.get(f"/api/marinas/{marina_id}/alarms/log", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert "alarms" in data
    assert len(data["alarms"]) >= 1
    for alarm in data["alarms"]:
        assert alarm["marina_id"] == marina_id


def test_alarm_log_filtered_by_marina(client, admin_headers, marina_id, restricted_marina_id):
    _seed_alarm(restricted_marina_id, pedestal_id=50)
    r = client.get(f"/api/marinas/{marina_id}/alarms/log", headers=admin_headers)
    assert r.status_code == 200
    for alarm in r.json()["alarms"]:
        assert alarm["marina_id"] == marina_id


def test_manager_blocked_from_restricted_marina_alarms(
    client, manager_headers, restricted_marina_id
):
    r = client.get(f"/api/marinas/{restricted_marina_id}/alarms/log", headers=manager_headers)
    assert r.status_code == 403


def _cabinet_alarm(aid=100, pedestal_id=1, alarm_type="temperature"):
    # AlarmResponse, Cloud_IOT routers/alarms.py:13-27
    return {"id": aid, "alarm_type": alarm_type, "source": "mqtt", "pedestal_id": pedestal_id,
            "status": "triggered", "severity": None, "message": "Temperature above 50",
            "details": None, "triggered_at": "2026-10-12T09:00:00", "acknowledged_at": None,
            "acknowledged_by": None, "resolved_at": None}


def test_acknowledge_alarm_writes_audit_log(client, admin_headers, marina_id, sim,
                                            setup_test_database):
    sim.state.sim.alarms = [_cabinet_alarm(100)]
    r = client.post(f"/api/marinas/{marina_id}/alarms/100/acknowledge", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["acknowledged"] is True and data["alarm_id"] == 100
    assert data["cabinet_acknowledged"] is True

    from tests.conftest import TestSession
    from app.models.cache import AuditLog
    from app.models.user import User

    db = TestSession()
    try:
        user = db.query(User).filter(User.email == "superadmin@test.erp").first()
        entry = (
            db.query(AuditLog)
            .filter(
                AuditLog.marina_id == marina_id,
                AuditLog.action == "acknowledge_alarm",
                AuditLog.target_id == 100,
                AuditLog.user_id == user.id,
            )
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert entry is not None and entry.performed_at is not None
        assert entry.details["outcome"] == "ok"
    finally:
        db.close()


def test_acknowledge_when_cabinet_is_away_says_so(client, admin_headers, marina_id, sim):
    sim.state.sim.fail_next = [500] * 10
    r = client.post(f"/api/marinas/{marina_id}/alarms/100/acknowledge", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["cabinet_acknowledged"] is False
    assert r.json()["outcome"]["code"] == "no_contact"


def test_active_alarms_proxied_from_pedestal(client, admin_headers, marina_id, sim):
    sim.state.sim.alarms = [_cabinet_alarm(1)]
    r = client.get(f"/api/marinas/{marina_id}/alarms/active", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["is_stale"] is False
    assert data["alarms"] == [_cabinet_alarm(1)]


def test_unauthenticated_alarm_log_returns_401(client, marina_id):
    r = client.get(f"/api/marinas/{marina_id}/alarms/log")
    assert r.status_code == 401
