"""Shared by the Krk scripts: run the cabinet's own code, against the live databases.

Run every script AS THE SERVICE USER, never as root:

    sudo -u cloud-iot /opt/cloud-iot/backend/.venv/bin/python /tmp/krk/<script>.py

As root, SQLite would create -wal/-shm files owned by root and the backend
(User=cloud-iot) could no longer write its own database.

Written against the cabinet's code at aa1f74f (what Krk runs).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path("/opt/cloud-iot/backend")
PEDESTAL_DB = BACKEND / "pedestal.db"
USERS_DB = BACKEND / "data" / "users.db"
SERVICE_USER = "cloud-iot"
ORIG_CWD = Path.cwd()

# a terminal that is not UTF-8 garbles č/ž, it must not crash a run half-way
for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(errors="backslashreplace")


def die(msg: str, code: int = 2) -> None:
    print(f"STOP: {msg}", file=sys.stderr)
    raise SystemExit(code)


def require_service_user() -> None:
    import pwd
    me = pwd.getpwuid(os.geteuid()).pw_name
    if me != SERVICE_USER:
        die(f"pokreni kao {SERVICE_USER} (sudo -u {SERVICE_USER} ...), ne kao {me}")


def enter_backend() -> None:
    """cwd = backend (the app reads .env and ./pedestal.db relative to it), app importable."""
    if not (BACKEND / "app" / "main.py").is_file():
        die(f"{BACKEND}/app/main.py ne postoji")
    global ORIG_CWD
    ORIG_CWD = Path.cwd()
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))


def assert_app_points_at_live_dbs() -> None:
    """Refuse to run if the app's engines resolve to any other file than the two above."""
    from app.database import engine
    from app.auth.user_database import user_engine
    ped = Path(engine.url.database or "").resolve()
    usr = Path(user_engine.url.database or "").resolve()
    if ped != PEDESTAL_DB.resolve():
        die(f"aplikacija gleda {ped}, ne {PEDESTAL_DB}")
    if usr != USERS_DB.resolve():
        die(f"aplikacija gleda {usr}, ne {USERS_DB}")


def require_backup(path: str | None, table: str) -> Path:
    """--apply only after a backup: the file exists, is SQLite, holds `table`, is intact."""
    import sqlite3
    if not path:
        die("--apply traži --backup <putanja kopije iz krk_backup.py>")
    p = Path(path)
    if not p.is_absolute():
        p = ORIG_CWD / p                  # relative to where you ran it, not to backend/
    if not p.is_file():
        die(f"kopija {p} ne postoji")
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
        has = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                          (table,)).fetchone()
    finally:
        con.close()
    if ok != "ok" or not has:
        die(f"kopija {p} nije ispravna (integrity={ok}, tablica {table}: {bool(has)})")
    return p
