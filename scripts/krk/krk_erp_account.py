"""2 · The ERP's service account on the cabinet: erp@lika.solutions, role api_client.

    # look (changes nothing): lists accounts, says what it would create
    sudo -u cloud-iot /opt/cloud-iot/backend/.venv/bin/python /tmp/krk/krk_erp_account.py

    # create
    sudo -u cloud-iot /opt/cloud-iot/backend/.venv/bin/python /tmp/krk/krk_erp_account.py \
         --apply --backup /var/backups/cloud-iot-erp/users-<stamp>.db

Creates the account through the cabinet's own handler (routers/auth.py
create_user, aa1f74f:215-243) — the same validation, hashing and
must_change_password=False an admin gets from the UI for an api_client.

api_client: token only from POST /api/auth/service-token (auth.py:30-69); its
JWT is refused by every operator route (auth/dependencies.py:41-46), so it
cannot open the gateway configuration; on /api/ext/* it gets exactly what
allowed_endpoints allows.

The password: random, 32 characters, written ONCE, straight to the terminal
(/dev/tty) — not to stdout, so a redirect, pipe or log never sees it. If there
is no terminal, nothing is created. Any existing account, MarinaMaster's
included, is only listed, never touched.
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from krk_common import (assert_app_points_at_live_dbs, die, enter_backend,  # noqa: E402
                        require_backup, require_service_user)

EMAIL = "erp@lika.solutions"
ROLE = "api_client"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup")
    a = ap.parse_args()
    require_service_user()
    enter_backend()

    from app.database import import_all_models
    import_all_models()
    assert_app_points_at_live_dbs()
    from app.auth.models import User
    from app.auth.password import verify_password
    from app.auth.schemas import UserCreate
    from app.auth.user_database import UserSessionLocal
    from app.routers.auth import create_user

    db = UserSessionLocal()
    try:
        users = db.query(User).order_by(User.id).all()
        print(f"Računi u users.db ({len(users)}) — samo popis, nijedan se ne mijenja:")
        for u in users:
            print(f"  id={u.id:<4} {u.email:40s} role={u.role:20s} active={bool(u.is_active)}")
        existing = next((u for u in users if u.email.lower() == EMAIL), None)
        if existing:
            print(f"\nRačun {EMAIL} VEĆ POSTOJI (id={existing.id}, role={existing.role}, "
                  f"active={bool(existing.is_active)}). Ne diram ga. Javi i odlučujemo.")
            raise SystemExit(3)
        if not a.apply:
            print(f"\nBez --apply: stvorio bih {EMAIL}, role={ROLE}, active=True, "
                  f"must_change_password=False, nasumična lozinka 32 znaka.")
            return

        require_backup(a.backup, "users")
        try:
            tty = open("/dev/tty", "w")
        except OSError:
            die("nema terminala (/dev/tty) — lozinku ne mogu pokazati samo tebi; ništa nije stvoreno")

        pw = secrets.token_urlsafe(24)               # 32 chars, ~192 bits
        assert len(pw) >= 24
        created = create_user(body=UserCreate(email=EMAIL, password=pw, role=ROLE), _=None, db=db)
        u = db.get(User, created.id)
        if not (u and u.role == ROLE and u.is_active and not u.must_change_password
                and verify_password(pw, u.password_hash)):
            die("račun stvoren, ali provjera nije prošla — javi mi prije ičega drugog", 4)
        print(f"\nSTVOREN: id={u.id} {u.email} role={u.role} active={bool(u.is_active)} "
              f"must_change_password={bool(u.must_change_password)}")
        tty.write("\n" + "=" * 60 + "\n"
                  f"  LOZINKA za {EMAIL} — prikazuje se samo ovaj put:\n\n"
                  f"      {pw}\n\n"
                  "  Spremi je u svoj upravitelj lozinki, pa očisti ekran (clear).\n"
                  + "=" * 60 + "\n")
        tty.close()
        del pw
    finally:
        db.close()


if __name__ == "__main__":
    main()
