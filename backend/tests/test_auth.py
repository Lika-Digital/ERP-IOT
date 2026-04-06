"""
test_auth.py — Authentication tests.

Verifies:
- Login returns JWT with correct role + marina_ids
- super_admin gets marina_ids=[] (signals all marinas)
- marina_manager gets only their assigned marina IDs
- 401 on unauthenticated endpoints
- 401 on wrong password
- Inactive user cannot login
"""
import pytest


def test_super_admin_login_returns_jwt(client):
    r = client.post("/api/auth/login", json={
        "email": "superadmin@test.erp",
        "password": "superadmin1234",
    })
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_super_admin_jwt_has_correct_role(client):
    r = client.post("/api/auth/login", json={
        "email": "superadmin@test.erp",
        "password": "superadmin1234",
    })
    token = r.json()["access_token"]
    # Decode without verifying (just inspect claims) — use base64 decode
    import base64, json as _json
    payload_b64 = token.split(".")[1]
    # Add padding if needed
    payload_b64 += "=" * (4 - len(payload_b64) % 4)
    payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
    assert payload["role"] == "super_admin"


def test_super_admin_marina_ids_empty(client):
    """super_admin gets marina_ids=[] meaning all marinas."""
    r = client.post("/api/auth/login", json={
        "email": "superadmin@test.erp",
        "password": "superadmin1234",
    })
    token = r.json()["access_token"]
    import base64, json as _json
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (4 - len(payload_b64) % 4)
    payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
    assert payload["marina_ids"] == []


def test_marina_manager_login_returns_jwt(client):
    r = client.post("/api/auth/login", json={
        "email": "manager@test.erp",
        "password": "manager1234",
    })
    assert r.status_code == 200


def test_marina_manager_sees_only_assigned_marinas(client, marina_id):
    r = client.post("/api/auth/login", json={
        "email": "manager@test.erp",
        "password": "manager1234",
    })
    token = r.json()["access_token"]
    import base64, json as _json
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (4 - len(payload_b64) % 4)
    payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
    assert marina_id in payload["marina_ids"]
    # Should NOT contain the restricted marina (which manager has no access to)
    assert len(payload["marina_ids"]) == 1


def test_wrong_password_returns_401(client):
    r = client.post("/api/auth/login", json={
        "email": "superadmin@test.erp",
        "password": "wrongpassword",
    })
    assert r.status_code == 401


def test_unknown_email_returns_401(client):
    r = client.post("/api/auth/login", json={
        "email": "nobody@test.erp",
        "password": "whatever",
    })
    assert r.status_code == 401


def test_inactive_user_cannot_login(client):
    r = client.post("/api/auth/login", json={
        "email": "inactive@test.erp",
        "password": "inactive1234",
    })
    assert r.status_code in (401, 403)


def test_unauthenticated_me_returns_401(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_returns_user_info(client, admin_headers):
    r = client.get("/api/auth/me", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "super_admin"
    assert data["email"] == "superadmin@test.erp"
    assert "marina_ids" in data


def test_me_marina_manager_sees_assigned_marinas(client, manager_headers, marina_id):
    r = client.get("/api/auth/me", headers=manager_headers)
    assert r.status_code == 200
    data = r.json()
    assert marina_id in data["marina_ids"]


def test_unauthenticated_marinas_returns_401(client):
    r = client.get("/api/marinas")
    assert r.status_code == 401


def test_unauthenticated_dashboard_returns_401(client, marina_id):
    r = client.get(f"/api/marinas/{marina_id}/dashboard")
    assert r.status_code == 401


def test_refresh_token(client, admin_headers):
    """Refresh should return a new valid token."""
    r = client.post("/api/auth/refresh", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
