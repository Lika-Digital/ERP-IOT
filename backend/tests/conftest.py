"""
Test fixtures for ERP-IOT backend.

Strategy:
- Use FastAPI TestClient (synchronous)
- Override DATABASE_URL to SQLite in-memory before importing app
- Seed: super_admin user, marina_manager user, one marina, access grant
"""
import os
import pytest

# ── Set env vars BEFORE importing the app ─────────────────────────────────────
os.environ["DATABASE_URL"] = "sqlite:///./tests/test_erp.db"
os.environ["JWT_SECRET"] = "test-secret-for-erp-iot-ci"
os.environ["DEFAULT_ADMIN_EMAIL"] = "admin@test.erp"
os.environ["DEFAULT_ADMIN_PASSWORD"] = "testadmin1234"
# Test encryption key — valid Fernet key for testing only
os.environ["ERP_ENCRYPTION_KEY"] = "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.utils.time import utcnow

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
    import app.models  # noqa: F401 — every model

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

        # Marina — encrypt test credentials
        from app.utils.encryption import encrypt_password
        marina_obj = Marina(
            name="Test Marina",
            location="Test Harbor",
            timezone="UTC",
            pedestal_api_base_url="http://pedestal-sw.test",
            pedestal_service_email="erp@test.service",
            pedestal_service_password_encrypted=encrypt_password("test-service-pass-123"),
            webhook_secret="test-webhook-secret",
            status="active",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db.add(marina_obj)
        db.flush()

        # Second marina (manager has no access)
        marina2 = Marina(
            name="Restricted Marina",
            location="Restricted Harbor",
            timezone="UTC",
            pedestal_api_base_url="http://pedestal-sw2.test",
            pedestal_service_email="erp@test2.service",
            pedestal_service_password_encrypted=encrypt_password("test-service-pass-456"),
            status="active",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db.add(marina2)
        db.flush()

        # Grant manager access to marina 1 only
        db.add(UserMarinaAccess(
            user_id=manager.id,
            marina_id=marina_obj.id,
            granted_at=utcnow(),
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


# ─── Cabinet simulator (spec §9.1) ────────────────────────────────────────────

async def _no_sleep(_seconds):
    return None


@pytest.fixture
def sim(setup_test_database):
    """The real ERP app and the real cabinet client, talking to the simulator.

    The simulator runs in-process through httpx.ASGITransport; credentials are
    the seeded Test Marina's. Backoff waits are skipped (the waits themselves
    are asserted in test_cabinet_client.py). Yields the simulator app; a test changes
    `sim.state.sim` to set up a scenario.
    """
    import httpx
    from simulator.cabinet_sim import create_app, make_state
    from app.services.pedestal_api_factory import get_pedestal_factory

    state = make_state("full")
    state.service_email = "erp@test.service"
    state.service_password = "test-service-pass-123"
    sim_app = create_app(state)

    factory = get_pedestal_factory()
    factory._clients.clear()
    factory.transport = httpx.ASGITransport(app=sim_app)
    factory.sleep = _no_sleep
    try:
        yield sim_app
    finally:
        factory.transport = None
        factory.sleep = None
        factory._clients.clear()
        db = TestSession()
        try:
            from app.models.cache import PedestalCache
            db.query(PedestalCache).delete()
            db.commit()
        finally:
            db.close()


@pytest.fixture
def cabinet_config(tmp_path, monkeypatch):
    """Write an ERP_CABINETS_FILE for the seeded marina; returns a setter."""
    import json

    def write(marina_id, device_type, berths):
        p = tmp_path / "cabinets.json"
        p.write_text(json.dumps({"marinas": {str(marina_id): {
            "device_type": device_type, "berths": berths}}}), encoding="utf-8")
        monkeypatch.setenv("ERP_CABINETS_FILE", str(p))
        return p

    return write
