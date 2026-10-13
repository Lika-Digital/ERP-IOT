"""D20 — users, sign-in and secrets (spec §4.9, §5.3, §7.1, §8.3).

Each test makes its own users, so a lockout or a 2FA reset here never touches
the seeded admin and manager every other test signs in with.
"""
import uuid
from datetime import timedelta

import pytest

from tests.conftest import TestSession, full_login, totp_now

PW = "correct horse battery"


def _db():
    return TestSession()


def _user(role="marina_manager", *, password=PW, enrolled=True, active=True):
    """A fresh user straight in the database. Returns (email, secret or None)."""
    from app.models.user import User
    from app.services import accounts
    from app.utils import totp
    from app.utils.encryption import encrypt_password
    from app.utils.time import utcnow

    email = f"d20-{uuid.uuid4().hex[:10]}@test.erp"
    secret = totp.new_secret() if enrolled else None
    db = _db()
    try:
        db.add(User(email=email, role=role, is_active=active, failed_count=0,
                    password_hash=accounts.pwd_ctx.hash(password) if password else None,
                    totp_secret_enc=encrypt_password(secret) if secret else None,
                    totp_confirmed_at=utcnow() if enrolled else None, created_at=utcnow()))
        db.commit()
    finally:
        db.close()
    return email, secret


def _get(email):
    from app.models.user import User
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        db.expunge(u)
        return u
    finally:
        db.close()


def _set(email, **fields):
    from app.models.user import User
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        for k, v in fields.items():
            setattr(u, k, v)
        db.commit()
    finally:
        db.close()


def _audit(email):
    from app.models.user import AuthAudit
    db = _db()
    try:
        return [(a.event, a.detail) for a in
                db.query(AuthAudit).filter(AuthAudit.email_tried == email).order_by(AuthAudit.id)]
    finally:
        db.close()


def _mfa(client, email, password=PW):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["mfa_token"]


def _bearer(t):
    return {"Authorization": f"Bearer {t}"}


# ─── TOTP: RFC 6238 Appendix B (SHA-1 rows) ──────────────────────────────────

RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"   # base32 of ASCII "12345678901234567890"


@pytest.mark.parametrize("t,code", [
    (59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"),
    (1234567890, "89005924"), (2000000000, "69279037"), (20000000000, "65353130"),
])
def test_totp_matches_rfc6238_test_vectors(t, code):
    from app.utils import totp
    assert totp.code_at(RFC_SECRET, t, digits=8) == code


def test_totp_window_is_one_step_each_way_and_no_more():
    from app.utils import totp
    now = 1_700_000_000
    for drift, ok in ((-60, False), (-30, True), (0, True), (30, True), (60, False)):
        code = totp.code_at(RFC_SECRET, now + drift)
        assert (totp.verify(RFC_SECRET, code, None, unix_time=now) is not None) is ok, drift


def test_totp_same_step_never_works_twice():
    from app.utils import totp
    now = 1_700_000_000
    code = totp.code_at(RFC_SECRET, now)
    step = totp.verify(RFC_SECRET, code, None, unix_time=now)
    assert step is not None
    assert totp.verify(RFC_SECRET, code, step, unix_time=now) is None


def test_totp_refuses_garbage_without_error():
    from app.utils import totp
    for bad in ("", "12345", "1234567", "abcdef", "12 34 5x"):
        assert totp.verify(RFC_SECRET, bad, None) is None


# ─── second factor is mandatory ──────────────────────────────────────────────

def test_mfa_token_opens_no_protected_route(client, marina_id):
    """Spec §7.1 'bez 2FA nema rada': every protected route, with an mfa token -> 401."""
    from tests.test_foundations import _concrete, _routes
    email, _ = _user()
    mfa = _mfa(client, email)
    checked = 0
    for method, path, protected in _routes():
        if not protected:
            continue
        r = client.request(method, _concrete(path), headers=_bearer(mfa))
        assert r.status_code == 401, f"{method} {path} -> {r.status_code} with an mfa token"
        checked += 1
    assert checked >= 27


def test_user_without_2fa_gets_only_enrolment(client):
    email, _ = _user(enrolled=False)
    r = client.post("/api/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200 and r.json()["mfa_enrolled"] is False
    mfa = r.json()["mfa_token"]
    assert client.post("/api/auth/mfa/verify", json={"code": "123456"},
                       headers=_bearer(mfa)).status_code == 409
    assert client.get("/api/auth/me", headers=_bearer(mfa)).status_code == 401


def test_enrolment_links_2fa_and_returns_ten_backup_codes_once(client):
    from app.models.user import UserBackupCode
    email, _ = _user(enrolled=False)
    mfa = _mfa(client, email)
    start = client.post("/api/auth/mfa/enroll/start", headers=_bearer(mfa)).json()
    assert start["otpauth_uri"].startswith("otpauth://totp/") and "<svg" in start["qr_svg"]
    assert start["secret"] in start["otpauth_uri"]
    assert client.post("/api/auth/mfa/enroll/confirm", json={"code": "000000"},
                       headers=_bearer(mfa)).status_code == 401
    done = client.post("/api/auth/mfa/enroll/confirm", json={"code": totp_now(start["secret"])},
                       headers=_bearer(mfa))
    assert done.status_code == 200, done.text
    codes = done.json()["backup_codes"]
    assert len(codes) == 10 and len(set(codes)) == 10
    assert client.get("/api/auth/me", headers=_bearer(done.json()["access_token"])).status_code == 200
    # stored as bcrypt, never in clear; secret stored encrypted
    u = _get(email)
    assert u.totp_confirmed_at is not None and start["secret"] not in (u.totp_secret_enc or "")
    db = _db()
    try:
        hashes = [r.code_hash for r in db.query(UserBackupCode).filter_by(user_id=u.id)]
    finally:
        db.close()
    assert len(hashes) == 10 and all(h.startswith("$2") for h in hashes)
    assert not any(c.replace("-", "") in h for c in codes for h in hashes)
    # a second enrolment over a linked 2FA is refused
    mfa2 = _mfa(client, email)
    assert client.post("/api/auth/mfa/enroll/start", headers=_bearer(mfa2)).status_code == 409


def test_backup_code_works_exactly_once(client):
    email, _ = _user(enrolled=False)
    mfa = _mfa(client, email)
    secret = client.post("/api/auth/mfa/enroll/start", headers=_bearer(mfa)).json()["secret"]
    codes = client.post("/api/auth/mfa/enroll/confirm", json={"code": totp_now(secret)},
                        headers=_bearer(mfa)).json()["backup_codes"]
    first = client.post("/api/auth/mfa/verify", json={"code": codes[3]},
                        headers=_bearer(_mfa(client, email)))
    assert first.status_code == 200
    again = client.post("/api/auth/mfa/verify", json={"code": codes[3]},
                        headers=_bearer(_mfa(client, email)))
    assert again.status_code == 401 and again.json() == {"detail": "Invalid code"}
    assert ("login_ok", "backup_code") in _audit(email)


def test_same_totp_code_never_signs_in_twice(client):
    email, secret = _user()
    code = totp_now(secret)
    assert client.post("/api/auth/mfa/verify", json={"code": code},
                       headers=_bearer(_mfa(client, email))).status_code == 200
    r = client.post("/api/auth/mfa/verify", json={"code": code},
                    headers=_bearer(_mfa(client, email)))
    assert r.status_code == 401 and r.json() == {"detail": "Invalid code"}


def test_every_2fa_refusal_says_the_same(client):
    email, secret = _user()
    mfa = _mfa(client, email)
    wrong = client.post("/api/auth/mfa/verify", json={"code": "000000"}, headers=_bearer(mfa))
    junk = client.post("/api/auth/mfa/verify", json={"code": "zz"}, headers=_bearer(mfa))
    code = totp_now(secret)
    assert client.post("/api/auth/mfa/verify", json={"code": code},
                       headers=_bearer(_mfa(client, email))).status_code == 200
    reused = client.post("/api/auth/mfa/verify", json={"code": code},
                         headers=_bearer(_mfa(client, email)))
    assert wrong.json() == junk.json() == reused.json() == {"detail": "Invalid code"}
    assert {wrong.status_code, junk.status_code, reused.status_code} == {401}


# ─── lockout ─────────────────────────────────────────────────────────────────

def test_five_failures_lock_password_and_2fa_add_up(client):
    email, secret = _user()
    for _ in range(3):
        assert client.post("/api/auth/login", json={"email": email, "password": "nope-nope-nope"}
                           ).status_code == 401
    mfa = _mfa(client, email)            # a right password does NOT clear the count
    for _ in range(2):
        assert client.post("/api/auth/mfa/verify", json={"code": "000000"},
                           headers=_bearer(mfa)).status_code == 401
    assert _get(email).locked_until is not None
    # locked: the right password AND a right code are refused, with the usual answer
    r = client.post("/api/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 401 and r.json() == {"detail": "Invalid email or password"}
    r = client.post("/api/auth/mfa/verify", json={"code": totp_now(secret)}, headers=_bearer(mfa))
    assert r.status_code == 401 and r.json() == {"detail": "Invalid code"}
    events = [e for e, _ in _audit(email)]
    assert "locked" in events and events.count("login_failed") >= 4
    assert ("login_failed", "locked") in _audit(email)
    # the lock is temporary
    from app.utils.time import utcnow
    _set(email, locked_until=utcnow() - timedelta(seconds=1), totp_last_step=None)
    assert full_login(client, email, PW, secret)


def test_success_resets_the_failure_count(client):
    email, secret = _user()
    for _ in range(4):
        client.post("/api/auth/login", json={"email": email, "password": "nope-nope-nope"})
    assert _get(email).failed_count == 4
    full_login(client, email, PW, secret)
    u = _get(email)
    assert u.failed_count == 0 and u.locked_until is None


# ─── tokens die with the 2FA they were issued under ─────────────────────────

def test_admin_reset_of_2fa_ends_the_users_sessions(client, admin_headers):
    email, secret = _user()
    token = full_login(client, email, PW, secret)
    assert client.get("/api/auth/me", headers=_bearer(token)).status_code == 200
    uid = _get(email).id
    r = client.post(f"/api/users/{uid}/mfa-reset", json={"reason": "phone lost"},
                    headers=admin_headers)
    assert r.status_code == 200 and r.json()["mfa_enrolled"] is False
    assert client.get("/api/auth/me", headers=_bearer(token)).status_code == 401
    assert ("mfa_reset", "phone lost") in _audit(email)
    # next sign-in goes to enrolment
    r = client.post("/api/auth/login", json={"email": email, "password": PW})
    assert r.json()["mfa_enrolled"] is False
    # and after linking a NEW 2FA the old token still opens nothing: it belongs
    # to the 2FA the admin reset (the token carries mfa_at)
    mfa = r.json()["mfa_token"]
    new_secret = client.post("/api/auth/mfa/enroll/start", headers=_bearer(mfa)).json()["secret"]
    assert client.post("/api/auth/mfa/enroll/confirm", json={"code": totp_now(new_secret)},
                       headers=_bearer(mfa)).status_code == 200
    assert client.get("/api/auth/me", headers=_bearer(token)).status_code == 401


def test_disabled_user_token_stops_working(client, admin_headers):
    email, secret = _user()
    token = full_login(client, email, PW, secret)
    uid = _get(email).id
    assert client.patch(f"/api/users/{uid}", json={"is_active": False},
                        headers=admin_headers).status_code == 200
    assert client.get("/api/auth/me", headers=_bearer(token)).status_code == 401


# ─── one-time setup link ─────────────────────────────────────────────────────

def _token_of(link: str) -> str:
    assert "/setup#token=" in link, "the token must travel in the fragment, never the query"
    return link.split("#token=", 1)[1]


def test_new_user_sets_password_and_links_2fa_through_the_link(client, admin_headers, marina_id):
    from app.models.user import SetupToken
    email = f"new-{uuid.uuid4().hex[:8]}@test.erp"
    r = client.post("/api/users", json={"email": email, "role": "marina_manager",
                                        "marina_ids": [marina_id]}, headers=admin_headers)
    assert r.status_code == 201, r.text
    assert r.json()["user"]["password_set"] is False
    token = _token_of(r.json()["setup"]["link"])
    # stored only as a hash
    db = _db()
    try:
        assert not db.query(SetupToken).filter(SetupToken.token_hash == token).count()
    finally:
        db.close()
    # nobody can sign in before the link is used — same answer as a wrong password
    assert client.post("/api/auth/login", json={"email": email, "password": PW}).status_code == 401

    assert client.post("/api/auth/setup/check", json={"token": token}).json() == {"email": email}
    assert client.post("/api/auth/setup", json={"token": token, "password": "short"}
                       ).status_code == 422
    r = client.post("/api/auth/setup", json={"token": token, "password": PW})
    assert r.status_code == 200 and r.json()["mfa_enrolled"] is False
    mfa = r.json()["mfa_token"]
    secret = client.post("/api/auth/mfa/enroll/start", headers=_bearer(mfa)).json()["secret"]
    done = client.post("/api/auth/mfa/enroll/confirm", json={"code": totp_now(secret)},
                       headers=_bearer(mfa))
    assert done.status_code == 200
    me = client.get("/api/auth/me", headers=_bearer(done.json()["access_token"])).json()
    assert me["role"] == "marina_manager" and me["marina_ids"] == [marina_id]
    # the link is used up
    assert client.post("/api/auth/setup", json={"token": token, "password": PW}).status_code == 410
    assert client.post("/api/auth/setup/check", json={"token": token}).status_code == 410


def test_setup_link_expires_and_a_new_one_cancels_the_old(client, admin_headers):
    from app.models.user import SetupToken
    from app.utils.time import utcnow
    email = f"exp-{uuid.uuid4().hex[:8]}@test.erp"
    r = client.post("/api/users", json={"email": email, "role": "admin"}, headers=admin_headers)
    uid, first = r.json()["user"]["id"], _token_of(r.json()["setup"]["link"])
    second = _token_of(client.post(f"/api/users/{uid}/setup-link",
                                   headers=admin_headers).json()["link"])
    assert client.post("/api/auth/setup/check", json={"token": first}).status_code == 410
    assert client.post("/api/auth/setup/check", json={"token": second}).status_code == 200
    db = _db()
    try:
        for row in db.query(SetupToken).filter(SetupToken.user_id == uid):
            row.created_at = utcnow() - timedelta(hours=48)
            row.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()
    assert client.post("/api/auth/setup", json={"token": second, "password": PW}).status_code == 410


def test_password_longer_than_bcrypt_reads_is_refused_not_truncated(client, admin_headers):
    email = f"long-{uuid.uuid4().hex[:8]}@test.erp"
    r = client.post("/api/users", json={"email": email, "role": "admin"}, headers=admin_headers)
    token = _token_of(r.json()["setup"]["link"])
    assert client.post("/api/auth/setup", json={"token": token, "password": "x" * 73}
                       ).status_code == 422


# ─── users: Admin only ───────────────────────────────────────────────────────

def test_marina_manager_cannot_see_or_change_users(client, manager_headers):
    for method, path, body in (
        ("GET", "/api/users", None), ("POST", "/api/users", {"email": "x@y.z", "role": "admin"}),
        ("PATCH", "/api/users/1", {"role": "marina_manager"}),
        ("POST", "/api/users/1/setup-link", None),
        ("POST", "/api/users/1/mfa-reset", {"reason": "because"}),
        ("POST", "/api/users/1/unlock", {"reason": "because"}),
        ("GET", "/api/users/audit", None),
    ):
        r = client.request(method, path, json=body, headers=manager_headers)
        assert r.status_code == 403, f"{method} {path} -> {r.status_code}"


def test_mfa_reset_needs_a_reason_and_never_on_yourself(client, admin_headers):
    email, _ = _user()
    uid = _get(email).id
    assert client.post(f"/api/users/{uid}/mfa-reset", json={}, headers=admin_headers
                       ).status_code == 422
    me = client.get("/api/auth/me", headers=admin_headers).json()["id"]
    assert client.post(f"/api/users/{me}/mfa-reset", json={"reason": "my own"},
                       headers=admin_headers).status_code == 409


def test_the_last_admin_cannot_be_removed_and_nobody_demotes_themselves(client, admin_headers):
    me = client.get("/api/auth/me", headers=admin_headers).json()["id"]
    assert client.patch(f"/api/users/{me}", json={"role": "marina_manager"},
                        headers=admin_headers).status_code == 409
    assert client.patch(f"/api/users/{me}", json={"is_active": False},
                        headers=admin_headers).status_code == 409


def test_user_changes_are_audited_with_the_admin_as_actor(client, admin_headers, marina_id):
    from app.models.user import AuthAudit
    email, _ = _user()
    uid = _get(email).id
    client.patch(f"/api/users/{uid}", json={"marina_ids": [marina_id]}, headers=admin_headers)
    admin_id = client.get("/api/auth/me", headers=admin_headers).json()["id"]
    db = _db()
    try:
        row = db.query(AuthAudit).filter(AuthAudit.user_id == uid,
                                         AuthAudit.event == "user_updated").one()
    finally:
        db.close()
    assert row.actor_id == admin_id and f"marinas=[{marina_id}]" in row.detail


def test_unknown_marina_is_refused_when_assigning(client, admin_headers):
    email, _ = _user()
    uid = _get(email).id
    assert client.patch(f"/api/users/{uid}", json={"marina_ids": [999999]},
                        headers=admin_headers).status_code == 422


# ─── first admin: no DEFAULT_ADMIN_PASSWORD (D20.3) ──────────────────────────

def test_default_admin_password_is_gone_from_settings_and_seeding():
    from app.config import Settings
    from app import database
    assert "default_admin_password" not in Settings.model_fields
    assert "default_admin_email" not in Settings.model_fields
    assert not hasattr(database, "_seed_defaults")


def test_setup_admin_cli_creates_an_admin_with_no_password(client, capsys):
    from app import setup_admin
    email = f"first-{uuid.uuid4().hex[:8]}@test.erp"
    import app.database as appdb
    real = appdb.SessionLocal
    appdb.SessionLocal = TestSession
    try:
        assert setup_admin.main(["--email", email, "--base-url", "https://erp.example"]) == 0
    finally:
        appdb.SessionLocal = real
    out = capsys.readouterr().out
    assert "https://erp.example/setup#token=" in out
    u = _get(email)
    assert u.role == "admin" and u.password_hash is None and u.totp_confirmed_at is None
    token = out.split("#token=", 1)[1].split()[0]
    assert client.post("/api/auth/setup/check", json={"token": token}).json() == {"email": email}
    assert ("setup_link_issued", "cli") in _audit(email)


def test_setup_admin_cli_refuses_an_existing_marina_manager(capsys):
    from app import setup_admin
    import app.database as appdb
    email, _ = _user(role="marina_manager")
    real = appdb.SessionLocal
    appdb.SessionLocal = TestSession
    try:
        assert setup_admin.main(["--email", email]) == 2
    finally:
        appdb.SessionLocal = real
    assert _get(email).role == "marina_manager"


# ─── WebSocket: a full token, nothing less ───────────────────────────────────

def test_websocket_needs_a_full_token(client, admin_headers):
    from starlette.websockets import WebSocketDisconnect
    email, _ = _user()
    mfa = _mfa(client, email)
    for query in ("", f"?token={mfa}", "?token=garbage"):
        # ping first: an accepted socket answers "pong" at once, so a broken
        # check fails this test instead of leaving it waiting for a message
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws" + query) as ws:
                ws.send_text("ping")
                assert ws.receive_text() != "pong", f"accepted without a full token: {query!r}"
        assert exc.value.code == 4001, query
    full = admin_headers["Authorization"].split()[1]
    with client.websocket_connect(f"/ws?token={full}") as ws:
        ws.send_text("ping")
        assert ws.receive_text() == "pong"


def test_auth_audit_records_the_real_reason(client):
    email, _ = _user(active=False)
    client.post("/api/auth/login", json={"email": email, "password": PW})
    assert ("login_failed", "account disabled") in _audit(email)


# ─── migration 010 on a database with users ──────────────────────────────────

def _alembic(env, *args):
    import subprocess
    import sys
    from pathlib import Path
    return subprocess.run([sys.executable, "-m", "alembic", *args],
                          cwd=str(Path(__file__).resolve().parent.parent),
                          capture_output=True, text=True, env=env)


def _mig_env(db):
    import os
    e = dict(os.environ)
    e.update({"DATABASE_URL": f"sqlite:///{db}", "JWT_SECRET": "mig-test"})
    return e


def test_migration_010_maps_super_admin_to_admin_and_keeps_passwords(tmp_path):
    """Existing users keep their password, become Admin / Marina Manager, and have
    no 2FA: their next sign-in is the enrolment screen (spec §7.1)."""
    import sqlite3
    db = tmp_path / "m.db"
    e = _mig_env(db)
    assert _alembic(e, "upgrade", "009").returncode == 0
    con = sqlite3.connect(db)
    con.execute("INSERT INTO users (email, password_hash, role, is_active, created_at) VALUES "
                "('old@x', '$2b$12$hash', 'super_admin', 1, '2026-01-01'),"
                "('mgr@x', '$2b$12$hash2', 'marina_manager', 1, '2026-01-01')")
    con.commit()
    con.close()
    r = _alembic(e, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    con = sqlite3.connect(db)
    rows = con.execute("SELECT email, role, password_hash, totp_confirmed_at, failed_count "
                       "FROM users ORDER BY email").fetchall()
    con.close()
    assert rows == [("mgr@x", "marina_manager", "$2b$12$hash2", None, 0),
                    ("old@x", "admin", "$2b$12$hash", None, 0)]


def test_migration_010_refuses_a_role_it_does_not_know(tmp_path):
    import sqlite3
    db = tmp_path / "m.db"
    e = _mig_env(db)
    assert _alembic(e, "upgrade", "009").returncode == 0
    con = sqlite3.connect(db)
    con.execute("INSERT INTO users (email, password_hash, role, is_active, created_at) VALUES "
                "('odd@x', 'h', 'operator', 1, '2026-01-01')")
    con.commit()
    con.close()
    r = _alembic(e, "upgrade", "head")
    assert r.returncode != 0 and "operator" in r.stderr


def test_websocket_marina_manager_hears_only_an_assigned_marina(client, manager_headers,
                                                               marina_id, restricted_marina_id):
    from starlette.websockets import WebSocketDisconnect
    tok = manager_headers["Authorization"].split()[1]
    for query in (f"?token={tok}", f"?token={tok}&marina_id={restricted_marina_id}"):
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws" + query) as ws:
                ws.send_text("ping")
                assert ws.receive_text() != "pong", f"manager accepted: {query!r}"
        assert exc.value.code == 4003, query
    with client.websocket_connect(f"/ws?token={tok}&marina_id={marina_id}") as ws:
        ws.send_text("ping")
        assert ws.receive_text() == "pong"
