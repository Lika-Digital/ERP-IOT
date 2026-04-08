"""
test_controls.py — Session control tests with audit logging.

Verifies:
- allow/deny/stop log user_id, marina_id, pedestal_id, action, timestamp to audit_log
- marina_manager blocked from controlling sessions in other marinas
"""
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_factory(return_value):
    """Return a factory mock whose get_client() returns a client mock."""
    mock_client = MagicMock()
    mock_client.allow_session = AsyncMock(return_value=return_value)
    mock_client.deny_session = AsyncMock(return_value=return_value)
    mock_client.stop_session = AsyncMock(return_value=return_value)
    mock_factory = MagicMock()
    mock_factory.get_client.return_value = mock_client
    return mock_factory, mock_client


def test_allow_session_logs_audit(client, admin_headers, marina_id, setup_test_database):
    mock_factory, _ = _mock_factory({"status": "allowed", "session_id": 1})
    with patch("app.routers.controls.get_pedestal_factory", return_value=lambda: mock_factory):
        from app.services.pedestal_api_factory import get_pedestal_factory as real_dep
        from app.main import app
        app.dependency_overrides[real_dep] = lambda: mock_factory

        r = client.post(
            f"/api/marinas/{marina_id}/sessions/1/allow",
            headers=admin_headers,
            params={"pedestal_id": 1},
        )
        app.dependency_overrides.clear()

    assert r.status_code == 200

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
                AuditLog.action == "allow_session",
                AuditLog.target_id == 1,
                AuditLog.user_id == user.id,
            )
            .order_by(AuditLog.performed_at.desc())
            .first()
        )
        assert entry is not None
        assert entry.marina_id == marina_id
        assert entry.pedestal_id == 1
        assert entry.performed_at is not None
    finally:
        db.close()


def test_deny_session_logs_audit_with_reason(client, admin_headers, marina_id, setup_test_database):
    mock_factory, _ = _mock_factory({"status": "denied", "session_id": 2})
    from app.services.pedestal_api_factory import get_pedestal_factory as real_dep
    from app.main import app
    app.dependency_overrides[real_dep] = lambda: mock_factory

    r = client.post(
        f"/api/marinas/{marina_id}/sessions/2/deny",
        headers=admin_headers,
        json={"reason": "No capacity"},
        params={"pedestal_id": 2},
    )
    app.dependency_overrides.clear()

    assert r.status_code == 200

    from tests.conftest import TestSession
    from app.models.cache import AuditLog

    db = TestSession()
    try:
        entry = (
            db.query(AuditLog)
            .filter(
                AuditLog.marina_id == marina_id,
                AuditLog.action == "deny_session",
                AuditLog.target_id == 2,
            )
            .order_by(AuditLog.performed_at.desc())
            .first()
        )
        assert entry is not None
        assert entry.details["reason"] == "No capacity"
    finally:
        db.close()


def test_stop_session_logs_audit(client, admin_headers, marina_id, setup_test_database):
    mock_factory, _ = _mock_factory({"status": "stopped", "session_id": 3})
    from app.services.pedestal_api_factory import get_pedestal_factory as real_dep
    from app.main import app
    app.dependency_overrides[real_dep] = lambda: mock_factory

    r = client.post(
        f"/api/marinas/{marina_id}/sessions/3/stop",
        headers=admin_headers,
        params={"pedestal_id": 3},
    )
    app.dependency_overrides.clear()

    assert r.status_code == 200

    from tests.conftest import TestSession
    from app.models.cache import AuditLog

    db = TestSession()
    try:
        entry = (
            db.query(AuditLog)
            .filter(
                AuditLog.marina_id == marina_id,
                AuditLog.action == "stop_session",
                AuditLog.target_id == 3,
            )
            .order_by(AuditLog.performed_at.desc())
            .first()
        )
        assert entry is not None
    finally:
        db.close()


def test_marina_manager_blocked_from_restricted_marina_controls(
    client, manager_headers, restricted_marina_id
):
    mock_factory, _ = _mock_factory({"status": "allowed"})
    from app.services.pedestal_api_factory import get_pedestal_factory as real_dep
    from app.main import app
    app.dependency_overrides[real_dep] = lambda: mock_factory

    r = client.post(
        f"/api/marinas/{restricted_marina_id}/sessions/1/allow",
        headers=manager_headers,
    )
    app.dependency_overrides.clear()

    assert r.status_code == 403


def test_marina_manager_can_control_own_marina(client, manager_headers, marina_id):
    mock_factory, _ = _mock_factory({"status": "allowed", "session_id": 10})
    from app.services.pedestal_api_factory import get_pedestal_factory as real_dep
    from app.main import app
    app.dependency_overrides[real_dep] = lambda: mock_factory

    r = client.post(
        f"/api/marinas/{marina_id}/sessions/10/allow",
        headers=manager_headers,
    )
    app.dependency_overrides.clear()

    assert r.status_code == 200


def test_unauthenticated_controls_return_401(client, marina_id):
    r = client.post(f"/api/marinas/{marina_id}/sessions/1/allow")
    assert r.status_code == 401
