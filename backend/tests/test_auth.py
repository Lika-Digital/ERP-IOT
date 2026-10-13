"""
test_auth.py — sign-in (D20, spec §7.1): password, then TOTP, for every user.

Verifies:
- a correct password gives only an mfa token; the full JWT needs the code
- admin gets marina_ids=[] (all marinas); marina_manager only assigned ones
- every refusal at the password step is the same 401 (O14), costs one bcrypt (O15)
- 401 on unauthenticated endpoints
"""
import base64
import json as _json

from tests.conftest import TOTP_SECRETS, full_login, totp_now


def _claims(token: str) -> dict:
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    return _json.loads(base64.urlsafe_b64decode(payload_b64))


def test_password_alone_gives_only_an_mfa_token(client):
    r = client.post("/api/auth/login", json={
        "email": "superadmin@test.erp",
        "password": "superadmin1234",
    })
    assert r.status_code == 200
    data = r.json()
    assert "access_token" not in data
    assert data["token_type"] == "mfa" and data["mfa_enrolled"] is True
    claims = _claims(data["mfa_token"])
    assert claims["scope"] == "mfa"
    assert "role" not in claims and "marina_ids" not in claims


def test_admin_full_token_has_role_and_all_marinas(client):
    claims = _claims(full_login(client, "superadmin@test.erp", "superadmin1234"))
    assert claims["role"] == "admin"
    assert claims["scope"] == "full"
    assert claims["marina_ids"] == []      # empty = all marinas


def test_marina_manager_sees_only_assigned_marinas(client, marina_id):
    claims = _claims(full_login(client, "manager@test.erp", "manager1234"))
    assert claims["role"] == "marina_manager"
    assert claims["marina_ids"] == [marina_id]


def test_wrong_password_returns_401(client):
    r = client.post("/api/auth/login", json={
        "email": "superadmin@test.erp",
        "password": "wrongpassword",
    })
    assert r.status_code == 401
    _unlock("superadmin@test.erp")


def test_unknown_email_returns_401(client):
    r = client.post("/api/auth/login", json={
        "email": "nobody@test.erp",
        "password": "whatever",
    })
    assert r.status_code == 401


def _unlock(email):
    """Wrong passwords count toward the lockout; keep the shared seed users usable."""
    from tests.conftest import TestSession
    from app.models.user import User
    db = TestSession()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.failed_count, u.locked_until = 0, None
        db.commit()
    finally:
        db.close()


def test_inactive_user_login_is_indistinguishable_from_wrong_password(client, caplog):
    """Ugasen racun s TOCNOM lozinkom i kriva lozinka daju ISTI odgovor.

    Do faze 1 ugasen racun je dobivao 403 "Account is disabled", sto je
    otkrivalo da racun postoji i da je lozinka tocna (enumeracija, spec §11
    O14). Odluceno: oba slucaja su isti 401 s istom porukom; razlog ide
    samo u log.
    """
    import logging

    disabled = client.post("/api/auth/login", json={
        "email": "inactive@test.erp",
        "password": "inactive1234",
    })
    wrong_pw = client.post("/api/auth/login", json={
        "email": "superadmin@test.erp",
        "password": "wrongpassword",
    })
    unknown = client.post("/api/auth/login", json={
        "email": "nobody@test.erp",
        "password": "whatever1234",
    })
    _unlock("superadmin@test.erp")
    assert disabled.status_code == wrong_pw.status_code == unknown.status_code == 401
    assert disabled.json() == wrong_pw.json() == unknown.json() == {
        "detail": "Invalid email or password"
    }

    with caplog.at_level(logging.WARNING, logger="app.routers.auth"):
        client.post("/api/auth/login", json={
            "email": "inactive@test.erp",
            "password": "inactive1234",
        })
    assert any("account disabled" in r.getMessage() for r in caplog.records), (
        "razlog odbijanja mora ostati u logu, inace operater ne zna zasto se "
        "korisnik ne moze prijaviti"
    )


def test_every_login_refusal_costs_exactly_one_bcrypt_check(client, monkeypatch):
    """Nepoznat e-mail placa istu bcrypt provjeru kao kriva lozinka (spec §11 O15).

    Bez toga nepoznat e-mail odgovara u mikrosekundama, a postojeci u ~200 ms:
    isti odgovor, razlicito vrijeme, enumeracija racuna po stoperici. Test
    broji provjere umjesto da mjeri vrijeme — mjerenje vremena u CI-ju je
    krhko, a broj provjera je tocno ono sto vrijeme odreduje.
    """
    from app.services import accounts

    calls = []
    real_verify = accounts.pwd_ctx.verify
    monkeypatch.setattr(
        accounts.pwd_ctx, "verify",
        lambda pw, h: calls.append(h) or real_verify(pw, h),
    )

    for email, pw in (
        ("nobody@test.erp", "whatever1234"),       # unknown email
        ("superadmin@test.erp", "wrongpassword"),  # wrong password
        ("inactive@test.erp", "inactive1234"),     # disabled account
    ):
        calls.clear()
        r = client.post("/api/auth/login", json={"email": email, "password": pw})
        assert r.status_code == 401
        assert len(calls) == 1, f"{email}: {len(calls)} bcrypt provjera, ocekivana 1"
    _unlock("superadmin@test.erp")


def test_dummy_hash_has_the_same_cost_as_real_hashes():
    """Lazni hash s nizim cost faktorom bio bi brzi — i opet bi odao racun."""
    from app.services import accounts

    real = accounts.pwd_ctx.hash("x")
    assert accounts.DUMMY_HASH.split("$")[2] == real.split("$")[2]


def test_unauthenticated_me_returns_401(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_returns_user_info(client, admin_headers):
    r = client.get("/api/auth/me", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "admin"
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
    """Refresh returns a new full token, and only for a full token."""
    r = client.post("/api/auth/refresh", headers=admin_headers)
    assert r.status_code == 200
    assert _claims(r.json()["access_token"])["scope"] == "full"


def test_refresh_refuses_an_mfa_token(client):
    mfa = client.post("/api/auth/login", json={"email": "superadmin@test.erp",
                                               "password": "superadmin1234"}).json()["mfa_token"]
    r = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {mfa}"})
    assert r.status_code == 401


def test_totp_secrets_in_the_fixture_are_valid_base32():
    for secret in TOTP_SECRETS.values():
        assert len(totp_now(secret)) == 6
