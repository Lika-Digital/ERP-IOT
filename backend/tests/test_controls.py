"""
test_controls.py — Session control tests with audit logging.

Verifies:
- allow/deny/stop log user_id, marina_id, pedestal_id, action, timestamp to audit_log
- marina_manager blocked from controlling sessions in other marinas
"""
import pytest
from unittest.mock import AsyncMock, patch


def test_allow_session_logs_audit(client, admin_headers, marina_id, setup_test_database):
    with patch(
        "app.routers.controls.PedestalAPIService.allow_session",
        new_callable=AsyncMock,
        return_value={"status": "allowed", "session_id": 1},
    ):
        r = client.post(
            f"/api/marinas/{marina_id}/sessions/1/allow",
            headers=admin_headers,
            params={"pedestal_id": 1},
        )

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
    with patch(
        "app.routers.controls.PedestalAPIService.deny_session",
        new_callable=AsyncMock,
        return_value={"status": "denied", "session_id": 2},
    ):
        r = client.post(
            f"/api/marinas/{marina_id}/sessions/2/deny",
            headers=admin_headers,
            json={"reason": "No capacity"},
            params={"pedestal_id": 2},
        )

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
    with patch(
        "app.routers.controls.PedestalAPIService.stop_session",
        new_callable=AsyncMock,
        return_value={"status": "stopped", "session_id": 3},
    ):
        r = client.post(
            f"/api/marinas/{marina_id}/sessions/3/stop",
            headers=admin_headers,
            params={"pedestal_id": 3},
        )

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
    """marina_manager should get 403 when trying to control sessions in unauthorized marina."""
    with patch(
        "app.routers.controls.PedestalAPIService.allow_session",
        new_callable=AsyncMock,
        return_value={"status": "allowed"},
    ):
        r = client.post(
            f"/api/marinas/{restricted_marina_id}/sessions/1/allow",
            headers=manager_headers,
        )

    assert r.status_code == 403


def test_marina_manager_can_control_own_marina(client, manager_headers, marina_id):
    """marina_manager should be able to control sessions in their assigned marina."""
    with patch(
        "app.routers.controls.PedestalAPIService.allow_session",
        new_callable=AsyncMock,
        return_value={"status": "allowed", "session_id": 10},
    ):
        r = client.post(
            f"/api/marinas/{marina_id}/sessions/10/allow",
            headers=manager_headers,
        )

    assert r.status_code == 200


def test_unauthenticated_controls_return_401(client, marina_id):
    r = client.post(f"/api/marinas/{marina_id}/sessions/1/allow")
    assert r.status_code == 401
