"""First admin, without DEFAULT_ADMIN_PASSWORD (D20.3, runbook §8.4 step 11a).

    python -m app.setup_admin --email admin@marina.hr [--name "Ime"] [--base-url https://erp.…]

Prints a one-time link, valid SETUP_LINK_MINUTES (30). Whoever opens it sets the
password and links 2FA before anything else. Nobody types a password here, and
none is stored until the link is used.

- No such user: an admin is created (no password, no 2FA).
- An existing admin: a new link (every earlier unused link stops working) —
  2FA stays as it is, so the link alone does not get past the second factor.
- An existing Marina Manager: refused; roles change on the Users screen.

Whoever can run this already holds the server; the link is audited all the same.
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.setup_admin")
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", default=None)
    ap.add_argument("--base-url", default=None,
                    help="where the UI is reached, e.g. https://erp.example (default PUBLIC_BASE_URL)")
    a = ap.parse_args(argv)
    # a console that is not UTF-8 garbles č/ž; it must not crash after the user exists
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")

    from .config import settings
    if a.base_url:
        settings.public_base_url = a.base_url
    from . import models  # noqa: F401 — every model
    from .database import SessionLocal
    from .models.user import User
    from .services import accounts
    from .utils.time import utcnow

    email = a.email.strip().lower()
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        if u is not None and u.role != "admin":
            print(f"STOP: {email} postoji i nije admin ({u.role}) — uloga se mijenja na zaslonu "
                  "Korisnici", file=sys.stderr)
            return 2
        created = u is None
        if created:
            u = User(email=email, full_name=a.name, role="admin", is_active=True,
                     password_hash=None, created_at=utcnow(), failed_count=0)
            db.add(u)
            db.flush()
            accounts.audit(db, "user_created", user=u, detail="role=admin; cli")
        link, expires = accounts.issue_setup_link(db, u, settings.setup_link_minutes)
        accounts.audit(db, "setup_link_issued", user=u, detail="cli")
        db.commit()
    finally:
        db.close()

    print(("Admin stvoren: " if created else "Novi link za postojećeg admina: ") + email)
    print(f"Jednokratni link (vrijedi do {expires:%Y-%m-%d %H:%M} UTC):")
    print(f"  {link}")
    print("Otvori ga preko Tailscalea, postavi lozinku i poveži 2FA prije ičega drugog.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
