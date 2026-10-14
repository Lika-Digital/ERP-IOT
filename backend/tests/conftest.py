"""
Test fixtures for ERP-IOT backend.

Strategy:
- Use FastAPI TestClient (synchronous)
- Override DATABASE_URL to SQLite in-memory before importing app
- Seed: admin, marina_manager (both with 2FA linked), one marina, access grant
- Sign-in is password + TOTP (D20); `full_login` does both steps
"""
import os
import pytest

# ── Set env vars BEFORE importing the app ─────────────────────────────────────
os.environ["DATABASE_URL"] = "sqlite:///./tests/test_erp.db"
os.environ["JWT_SECRET"] = "test-secret-for-erp-iot-ci"
# Test encryption key — valid Fernet key for testing only
os.environ["ERP_ENCRYPTION_KEY"] = "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
os.environ["COLLECTOR_ENABLED"] = "false"   # tests drive the collector themselves

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.utils.time import utcnow

TEST_DB_URL = "sqlite:///./tests/test_erp.db"

# Known TOTP secrets of the seeded users, so tests can compute their codes (RFC 6238).
TOTP_SECRETS = {
    "superadmin@test.erp": "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
    "manager@test.erp": "KRSXG5CTMVRXEZLUKRSXG5CTMVRXEZLU",
}
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
    from app.utils.encryption import encrypt_password as _enc

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

    db = TestSession()
    try:
        # Admin (D20; was super_admin), 2FA linked
        super_admin = User(
            email="superadmin@test.erp",
            password_hash=pwd_ctx.hash("superadmin1234"),
            full_name="Super Admin",
            role="admin",
            is_active=True,
            totp_secret_enc=_enc(TOTP_SECRETS["superadmin@test.erp"]),
            totp_confirmed_at=utcnow(),
        )
        db.add(super_admin)

        # Marina manager, 2FA linked
        manager = User(
            email="manager@test.erp",
            password_hash=pwd_ctx.hash("manager1234"),
            full_name="Marina Manager",
            role="marina_manager",
            is_active=True,
            totp_secret_enc=_enc(TOTP_SECRETS["manager@test.erp"]),
            totp_confirmed_at=utcnow(),
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


def totp_now(secret: str) -> str:
    import time
    from app.utils import totp
    return totp.code_at(secret, time.time())


def full_login(client, email: str, password: str, secret: str | None = None) -> str:
    """Password, then TOTP — the only way to a full token (D20).

    The same 30-second code never works twice (spec §7.1), and tests sign the
    same user in many times within one step; so the test forgets the last
    used step first. That is the only rule bent here, and only in tests.
    """
    from app.models.user import User
    db = TestSession()
    try:
        u = db.query(User).filter(User.email == email).first()
        if u is not None:
            u.totp_last_step = None
            db.commit()
    finally:
        db.close()
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    mfa = r.json()["mfa_token"]
    code = totp_now(secret or TOTP_SECRETS[email])
    r = client.post("/api/auth/mfa/verify", json={"code": code},
                    headers={"Authorization": f"Bearer {mfa}"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def super_admin_token(client):
    return full_login(client, "superadmin@test.erp", "superadmin1234")


@pytest.fixture(scope="session")
def manager_token(client):
    return full_login(client, "manager@test.erp", "manager1234")


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


def _clear_cabinets(marina_id):
    """Explicit order: the app's SQLite engine has no FK cascades (PRAGMA off)."""
    from app.models.berth import (Berth, BerthOutlet, BerthOutletCabinet, MappingComparison,
                                  OutletNfcTag)
    from app.models.cabinet import Cabinet, CabinetCapability, Outlet
    from app.models.cache import AlarmLog
    from app.models.metering import (CommandAudit, ConsumptionInterval, ConsumptionMonthly,
                                     ErpSession, OutletMeterState, ReconciliationRun)
    from app.models.security import ServiceWindow

    db = TestSession()
    try:
        cab_ids = [c.id for c in db.query(Cabinet).filter(Cabinet.marina_id == marina_id)]
        berth_ids = [b.id for b in db.query(Berth).filter(Berth.marina_id == marina_id)]
        out_ids = [o.id for o in db.query(Outlet).filter(Outlet.cabinet_id.in_(cab_ids))]
        # phase 4 rows hang off cabinets and outlets too
        db.query(ConsumptionInterval).filter(ConsumptionInterval.outlet_id.in_(out_ids)).delete()
        db.query(OutletMeterState).filter(OutletMeterState.outlet_id.in_(out_ids)).delete()
        # the monthly aggregate is kept in production, but in tests an outlet id is
        # reused after the delete below, and a stale month would land on the new outlet
        db.query(ConsumptionMonthly).filter(ConsumptionMonthly.outlet_id.in_(out_ids)).delete()
        for model in (ErpSession, CommandAudit, ReconciliationRun, AlarmLog):
            db.query(model).filter(model.cabinet_id.in_(cab_ids)).delete()
        db.query(BerthOutlet).filter(BerthOutlet.berth_id.in_(berth_ids)).delete()
        db.query(Berth).filter(Berth.id.in_(berth_ids)).delete()
        db.query(OutletNfcTag).filter(OutletNfcTag.outlet_id.in_(out_ids)).delete()
        db.query(Outlet).filter(Outlet.id.in_(out_ids)).delete()
        for model in (CabinetCapability, MappingComparison, BerthOutletCabinet, ServiceWindow):
            db.query(model).filter(model.cabinet_id.in_(cab_ids)).delete()
        db.query(Cabinet).filter(Cabinet.id.in_(cab_ids)).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture
def cabinet_config(marina_id):
    """Provision the seeded marina's cabinet IN THE DATABASE (phase 3; phase 2
    wrote a file). write(marina_id, device_type, {cabinet_berth_id: [outlets]})
    creates the cabinet, one ERP berth per cabinet berth, and the mapping."""
    from app.services import cabinets as svc

    def write(mid, device_type, berths):
        _clear_cabinets(mid)
        db = TestSession()
        try:
            cab = svc.provision_cabinet(
                db, marina_id=mid, pedestal_pk=1, display_id="MAR_KRK_ORM_01",
                device_type=device_type, base_url="http://pedestal-sw.test",
                service_email="erp@test.service", service_password="test-service-pass-123")
            for cab_berth, outs in berths.items():
                b = svc.create_berth(db, marina_id=mid, berth_number=f"A-{int(cab_berth):02d}",
                                     cabinet_id=cab.id, cabinet_berth_id=int(cab_berth))
                svc.set_berth_outlets(db, b, list(outs), assigned_by="test@lika.digital")
            return cab.id
        finally:
            db.close()

    yield write
    _clear_cabinets(marina_id)
