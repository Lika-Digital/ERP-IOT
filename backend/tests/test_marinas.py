"""
test_marinas.py — Marina CRUD and access control tests.

Verifies:
- Marina creation (super_admin only)
- marina_manager cannot create a marina
- List returns only authorized marinas for marina_manager
- super_admin sees all marinas
- Service account fields are accepted; encrypted password is never returned
"""
import pytest
from datetime import datetime


def test_super_admin_can_create_marina(client, admin_headers):
    r = client.post("/api/marinas", headers=admin_headers, json={
        "name": "New Test Marina",
        "location": "New Harbor",
        "timezone": "Europe/Zagreb",
        "pedestal_api_base_url": "http://new-pedestal.test",
        "pedestal_service_email": "erp@new-marina.service",
        "pedestal_service_password": "super-secret-pass",
        "status": "active",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "New Test Marina"
    assert data["timezone"] == "Europe/Zagreb"
    # Plaintext password and encrypted blob must never be returned
    assert "pedestal_service_password" not in data
    assert "pedestal_service_password_encrypted" not in data
    # Email is returned (not sensitive)
    assert data["pedestal_service_email"] == "erp@new-marina.service"


def test_marina_manager_cannot_create_marina(client, manager_headers):
    r = client.post("/api/marinas", headers=manager_headers, json={
        "name": "Unauthorized Marina",
        "pedestal_api_base_url": "http://unauth.test",
        "pedestal_service_email": "x@x.test",
        "pedestal_service_password": "pass",
    })
    assert r.status_code == 403


def test_unauthenticated_cannot_create_marina(client):
    r = client.post("/api/marinas", json={
        "name": "Unauth Marina",
        "pedestal_api_base_url": "http://unauth.test",
        "pedestal_service_email": "x@x.test",
        "pedestal_service_password": "k",
    })
    assert r.status_code == 401


def test_super_admin_sees_all_marinas(client, admin_headers):
    r = client.get("/api/marinas", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    names = [m["name"] for m in data]
    assert "Test Marina" in names
    assert "Restricted Marina" in names


def test_marina_manager_sees_only_assigned_marinas(client, manager_headers):
    r = client.get("/api/marinas", headers=manager_headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    names = [m["name"] for m in data]
    assert "Test Marina" in names
    assert "Restricted Marina" not in names


def test_marina_manager_cannot_access_restricted_marina(client, manager_headers, restricted_marina_id):
    r = client.get(f"/api/marinas/{restricted_marina_id}", headers=manager_headers)
    assert r.status_code == 403


def test_super_admin_can_update_marina(client, admin_headers, marina_id):
    r = client.patch(f"/api/marinas/{marina_id}", headers=admin_headers, json={
        "location": "Updated Location"
    })
    assert r.status_code == 200
    assert r.json()["location"] == "Updated Location"


def test_marina_manager_cannot_update_marina(client, manager_headers, marina_id):
    r = client.patch(f"/api/marinas/{marina_id}", headers=manager_headers, json={
        "location": "Hacked Location"
    })
    assert r.status_code == 403


def test_get_nonexistent_marina_returns_404(client, admin_headers):
    r = client.get("/api/marinas/999999", headers=admin_headers)
    assert r.status_code == 404


def test_grant_and_revoke_access(client, admin_headers, restricted_marina_id, setup_test_database):
    """Grant manager access to restricted marina then revoke it."""
    from tests.conftest import TestSession
    from app.models.user import User
    db = TestSession()
    manager = db.query(User).filter(User.email == "manager@test.erp").first()
    manager_id = manager.id
    db.close()

    # Grant
    r = client.post(
        f"/api/marinas/{restricted_marina_id}/access",
        headers=admin_headers,
        json={"user_id": manager_id, "marina_id": restricted_marina_id},
    )
    assert r.status_code == 204

    # Revoke
    r = client.delete(
        f"/api/marinas/{restricted_marina_id}/access/{manager_id}",
        headers=admin_headers,
    )
    assert r.status_code == 204
