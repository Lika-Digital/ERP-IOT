"""
test_alarms.py — Alarm log and acknowledgment tests.

Verifies:
- acknowledge_alarm writes audit_log entry with user_id + timestamp
- alarm_log is filtered by marina_id
- marina_manager blocked from other marinas
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock


def _mock_factory(**methods):
    mock_client = MagicMock()
    for name, return_value in methods.items():
        setattr(mock_client, name, AsyncMock(return_value=return_value))
    mock_factory = MagicMock()
    mock_factory.get_client.return_value = mock_client
    return mock_factory


def _override(mock_factory):
    from app.services.pedestal_api_factory import get_pedestal_factory as real_dep
    from app.main import app
    app.dependency_overrides[real_dep] = lambda: mock_factory


def _clear():
    from app.main import app
    app.dependency_overrides.clear()


def _seed_alarm(marina_id: int, pedestal_id: int = 1) -> int:
    from tests.conftest import TestSession
    from app.models.cache import AlarmLog

    db = TestSession()
    try:
        entry = AlarmLog(
            marina_id=marina_id,
            pedestal_id=pedestal_id,
            alarm_data={"id": 100, "alarm_type": "temperature", "value": 60.0},
            received_at=datetime.utcnow(),
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


def test_acknowledge_alarm_writes_audit_log(client, admin_headers, marina_id, setup_test_database):
    factory = _mock_factory(acknowledge_alarm={"acknowledged": True})
    _override(factory)

    r = client.post(
        f"/api/marinas/{marina_id}/alarms/100/acknowledge",
        headers=admin_headers,
    )
    _clear()

    assert r.status_code == 200
    data = r.json()
    assert data["acknowledged"] is True
    assert data["alarm_id"] == 100

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
            .first()
        )
        assert entry is not None
        assert entry.performed_at is not None
    finally:
        db.close()


def test_active_alarms_proxied_from_pedestal(client, admin_headers, marina_id):
    mock_alarms = [{"id": 1, "alarm_type": "temperature"}]
    factory = _mock_factory(get_active_alarms=(mock_alarms, False))
    _override(factory)

    r = client.get(f"/api/marinas/{marina_id}/alarms/active", headers=admin_headers)
    _clear()

    assert r.status_code == 200
    data = r.json()
    assert data["is_stale"] is False
    assert data["alarms"] == mock_alarms


def test_unauthenticated_alarm_log_returns_401(client, marina_id):
    r = client.get(f"/api/marinas/{marina_id}/alarms/log")
    assert r.status_code == 401
