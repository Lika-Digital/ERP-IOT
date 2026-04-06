"""
Test fixtures for ERP-IOT backend.

Strategy:
- Use FastAPI TestClient (synchronous)
- Override DATABASE_URL to SQLite in-memory before importing app
- Seed: super_admin user, marina_manager user, one marina, access grant
"""
import os
import pytest
from unittest.mock import patch, AsyncMock

# ── Set env vars BEFORE importing the app ─────────────────────────────────────
os.environ["DATABASE_URL"] = "sqlite:///./tests/test_erp.db"
os.environ["JWT_SECRET"] = "test-secret-for-erp-iot-ci"
os.environ["DEFAULT_ADMIN_EMAIL"] = "admin@test.erp"
os.environ["DEFAULT_ADMIN_PASSWORD"] = "testadmin1234"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DB_URL = "sqlite:///./tests/test_erp.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create all tables and seed test data."""
    from app.database import Base
    from app.models import marina, user, cache  # noqa: F401

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    from app.models.marina import Marina
    from app.models.user import User, UserMarinaAccess
    from passlib.context import CryptContext

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

    db = TestSession()
    try:
        # Super admin
        super_admin = User(
            email="superadmin@test.erp",
            password_hash=pwd_ctx.hash("superadmin1234"),
            full_name="Super Admin",
            role="super_admin",
            is_active=True,
        )
        db.add(super_admin)

        # Marina manager
        manager = User(
            email="manager@test.erp",
            password_hash=pwd_ctx.hash("manager1234"),
            full_name="Marina Manager",
            role="marina_manager",
            is_active=True,
        )
        db.add(manager)

        # Inactive user
        inactive = User(
            email="inactive@test.erp",
            password_hash=pwd_ctx.hash("inactive1234"),
            full_name="Inactive User",
            role="marina_manager",
            is_active=False,
        )
        db.add(inactive)

        db.flush()  # get IDs

        # Marina
        from datetime import datetime
        marina_obj = Marina(
            name="Test Marina",
            location="Test Harbor",
            timezone="UTC",
            pedestal_api_base_url="http://pedestal-sw.test",
            pedestal_api_key="test-api-key-123",
            webhook_secret="test-webhook-secret",
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(marina_obj)
        db.flush()

        # Second marina (manager has no access)
        marina2 = Marina(
            name="Restricted Marina",
            location="Restricted Harbor",
            timezone="UTC",
            pedestal_api_base_url="http://pedestal-sw2.test",
            pedestal_api_key="test-api-key-456",
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(marina2)
        db.flush()

        # Grant manager access to marina 1 only
        db.add(UserMarinaAccess(
            user_id=manager.id,
            marina_id=marina_obj.id,
            granted_at=datetime.utcnow(),
            granted_by=super_admin.id,
        ))

        db.commit()
    finally:
        db.close()

    yield

    # Cleanup
    test_engine.dispose()
    import time
    for _ in range(5):
        try:
            os.remove("tests/test_erp.db")
            break
        except (FileNotFoundError, PermissionError):
            time.sleep(0.2)


@pytest.fixture(scope="session")
def client(setup_test_database):
    """TestClient with DB dependency overridden."""
    from app.main import app
    from app.database import get_db

    app.dependency_overrides[get_db] = override_get_db

    from starlette.testclient import TestClient
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def super_admin_token(client):
    r = client.post("/api/auth/login", json={
        "email": "superadmin@test.erp",
        "password": "superadmin1234",
    })
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def manager_token(client):
    r = client.post("/api/auth/login", json={
        "email": "manager@test.erp",
        "password": "manager1234",
    })
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(super_admin_token):
    return {"Authorization": f"Bearer {super_admin_token}"}


@pytest.fixture(scope="session")
def manager_headers(manager_token):
    return {"Authorization": f"Bearer {manager_token}"}


@pytest.fixture(scope="session")
def marina_id(setup_test_database):
    """Return the ID of the test marina (id=1 after seed)."""
    db = TestSession()
    try:
        from app.models.marina import Marina
        m = db.query(Marina).filter(Marina.name == "Test Marina").first()
        return m.id
    finally:
        db.close()


@pytest.fixture(scope="session")
def restricted_marina_id(setup_test_database):
    """Return the ID of the marina the manager cannot access."""
    db = TestSession()
    try:
        from app.models.marina import Marina
        m = db.query(Marina).filter(Marina.name == "Restricted Marina").first()
        return m.id
    finally:
        db.close()
