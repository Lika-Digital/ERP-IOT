"""The first admin, the way D20 makes one — for the boot, browser and growth checks.

There is no DEFAULT_ADMIN_PASSWORD (D20.3), so every check that needs a signed-in
user walks the real path: `python -m app.setup_admin` prints a one-time link,
the link sets a password, 2FA is linked with a TOTP code — and only then is
there a full token. A check that still seeded a password would test a path
production no longer has.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
from app.utils import totp  # noqa: E402 — stdlib only, does not boot the app's settings


def link_token(env: dict, email: str, cwd: str) -> str:
    """Run the CLI as the runbook does (§8.4 step 11a) and take the token from its link."""
    r = subprocess.run([sys.executable, "-m", "app.setup_admin", "--email", email],
                       cwd=cwd, env=env, capture_output=True, text=True)
    if r.returncode != 0 or "#token=" not in r.stdout:
        raise RuntimeError(f"setup_admin failed ({r.returncode}): {r.stdout[-500:]} {r.stderr[-1500:]}")
    return r.stdout.split("#token=", 1)[1].split()[0]


def enrol(post: Callable, token: str, password: str) -> dict:
    """Password through the link, then 2FA. `post(path, body, bearer)` -> (status, json).

    Returns access_token, the TOTP secret and the backup codes.
    """
    code, body = post("/api/auth/setup", {"token": token, "password": password}, None)
    if code != 200:
        raise RuntimeError(f"setup: {code} {body}")
    mfa = body["mfa_token"]
    code, body = post("/api/auth/mfa/enroll/start", None, mfa)
    if code != 200:
        raise RuntimeError(f"enrol start: {code} {body}")
    secret = body["secret"]
    code, body = post("/api/auth/mfa/enroll/confirm", {"code": totp.code_at(secret, time.time())}, mfa)
    if code != 200:
        raise RuntimeError(f"enrol confirm: {code} {body}")
    return {"access_token": body["access_token"], "secret": secret,
            "backup_codes": body["backup_codes"]}


def code_now(secret: str) -> str:
    return totp.code_at(secret, time.time())
