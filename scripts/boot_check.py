"""TC-ERP-BOOT-01a / BOOT-02 — the application actually starts.

Not a component test. A real migration on an empty database, a real uvicorn
process, real HTTP: health, login, an authenticated route. Spec §9.

It cannot pass empty:
  - every check is counted, and the script exits 0 only if ALL expected checks
    ran and passed — a check that never ran counts as a failure;
  - a server that does not come up is a failure, never a skip;
  - the negative check proves the boot path is the real one: without
    JWT_SECRET the same command must NOT come up.

The server runs from an empty temp directory with PYTHONPATH=backend, so
backend/.env on the author's machine cannot supply anything. What boots here is
what the gate's environment says, nothing else.

Usage:  backend/.venv/Scripts/python.exe scripts/boot_check.py
Env:    BOOT_DATABASE_URL  optional; default is a fresh SQLite file in a temp dir
                           (CI passes a Postgres URL)
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

ADMIN_EMAIL = "boot@check.erp"
ADMIN_PASSWORD = "boot-check-password"  # noqa: S105 — throwaway, temp DB only
STARTUP_TIMEOUT_S = 40

EXPECTED_CHECKS = [
    "migration: alembic upgrade head on empty database",
    "migration: alembic check - models and migrations agree (O17)",
    "schema: the database itself enforces the spec §4 rules (probes)",
    "negative: without JWT_SECRET the server does not come up",
    "server: uvicorn comes up",
    "GET /api/health -> 200, status ok",
    "POST /api/auth/login -> 200 + access_token",
    "GET /api/auth/me with token -> 200, same user",
    "GET /api/marinas with token -> 200",
    "GET /api/auth/me without token -> 401",
]

_passed: list[str] = []


def ok(name: str) -> None:
    assert name in EXPECTED_CHECKS, f"unknown check {name!r}"
    _passed.append(name)
    print(f"  [ok]   {name}", flush=True)


def _annotate(name: str, detail: str) -> None:
    """In GitHub Actions a failed check is also a public annotation: the raw log
    needs a login, an annotation does not."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        one_line = " | ".join(x.strip() for x in detail.splitlines() if x.strip())[:1500]
        print(f"::error title={name[:80]}::{one_line}", flush=True)


def fail(name: str, detail: str) -> None:
    print(f"  [FAIL] {name}\n         {detail}", flush=True)
    _annotate(name, detail)
    summary()
    sys.exit(1)


def summary() -> None:
    missing = [c for c in EXPECTED_CHECKS if c not in _passed]
    print(f"\n  BOOT: {len(_passed)}/{len(EXPECTED_CHECKS)} checks passed", flush=True)
    for c in missing:
        print(f"         not passed: {c}", flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http(method: str, url: str, body: dict | None = None, token: str | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 — 127.0.0.1 only
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def base_env(db_url: str) -> dict:
    e = {k: v for k, v in os.environ.items()
         if k not in ("JWT_SECRET", "DEFAULT_ADMIN_EMAIL", "DEFAULT_ADMIN_PASSWORD",
                      "ERP_ENCRYPTION_KEY", "DATABASE_URL")}
    e["PYTHONPATH"] = str(BACKEND)
    e["DATABASE_URL"] = db_url
    return e


def uvicorn_cmd(port: int) -> list[str]:
    return [sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"]


def main() -> int:
    print("TC-ERP-BOOT-01a - application boots for real\n", flush=True)

    # Windows may still hold the SQLite file for a moment after the server exits;
    # a leftover temp file is not a boot failure.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_url = os.environ.get("BOOT_DATABASE_URL") or f"sqlite:///{Path(tmp) / 'boot.db'}"

        # ── 1. real migration on an empty database ───────────────────────────
        name = EXPECTED_CHECKS[0]
        r = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(BACKEND), capture_output=True, text=True,
            env={**base_env(db_url), "JWT_SECRET": "boot-migration-only"},
        )
        if r.returncode != 0:
            fail(name, r.stderr.strip()[-2000:])
        ok(name)

        # ── 1b. the models describe exactly what the migrations built ──────
        # A model column no migration creates passes create_all-based tests and
        # breaks the first real deployment. (spec §11 O17)
        name = EXPECTED_CHECKS[1]
        r = subprocess.run(
            [sys.executable, "-m", "alembic", "check"],
            cwd=str(BACKEND), capture_output=True, text=True,
            env={**base_env(db_url), "JWT_SECRET": "boot-migration-only"},
        )
        if r.returncode != 0:
            fail(name, (r.stdout + r.stderr).strip()[-2000:])
        ok(name)

        # ── 1c. CHECKs and triggers — alembic check does not compare them ──
        name = EXPECTED_CHECKS[2]
        sys.path.insert(0, str(ROOT / "scripts"))
        import schema_probes
        from sqlalchemy import create_engine
        eng = create_engine(db_url)
        try:
            results = schema_probes.run(eng)
        finally:
            eng.dispose()
        bad = [f"{n}: {d}" for n, good, d in results if not good]
        if bad or not results:
            fail(name, "\n         ".join(bad) or "no probes ran")
        ok(name)
        print(f"         {len(results)} probes, all held", flush=True)

        # ── 2. negative: no JWT_SECRET -> must not come up ───────────────────
        name = EXPECTED_CHECKS[3]
        port = free_port()
        p = subprocess.Popen(uvicorn_cmd(port), cwd=tmp, env=base_env(db_url),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            out, _ = p.communicate(timeout=STARTUP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate()
            fail(name, "server kept running without JWT_SECRET (fail-fast is gone)")
        if p.returncode == 0 or "JWT_SECRET" not in out:
            fail(name, f"exit={p.returncode}, expected non-zero mentioning JWT_SECRET:\n{out[-1500:]}")
        ok(name)

        # ── 3. real server ───────────────────────────────────────────────────
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        env = {
            **base_env(db_url),
            "JWT_SECRET": "boot-check-secret-" + os.urandom(8).hex(),
            "DEFAULT_ADMIN_EMAIL": ADMIN_EMAIL,
            "DEFAULT_ADMIN_PASSWORD": ADMIN_PASSWORD,
            "ERP_ENCRYPTION_KEY": "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=",
        }
        log_path = Path(tmp) / "uvicorn.log"
        log_f = open(log_path, "w", encoding="utf-8")
        srv = subprocess.Popen(uvicorn_cmd(port), cwd=tmp, env=env,
                               stdout=log_f, stderr=subprocess.STDOUT)
        try:
            name = EXPECTED_CHECKS[4]
            deadline = time.monotonic() + STARTUP_TIMEOUT_S
            up = False
            while time.monotonic() < deadline:
                if srv.poll() is not None:
                    break
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=1):
                        up = True
                        break
                except OSError:
                    time.sleep(0.3)
            if not up:
                log_f.flush()
                fail(name, f"server did not come up (exit={srv.poll()}):\n"
                           + log_path.read_text(encoding="utf-8")[-2000:])
            ok(name)

            name = EXPECTED_CHECKS[5]
            code, body = http("GET", f"{base}/api/health")
            if code != 200 or json.loads(body).get("status") != "ok":
                fail(name, f"{code} {body[:300]}")
            ok(name)

            name = EXPECTED_CHECKS[6]
            code, body = http("POST", f"{base}/api/auth/login",
                              {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
            token = json.loads(body).get("access_token") if code == 200 else None
            if not token:
                fail(name, f"{code} {body[:300]}")
            ok(name)

            name = EXPECTED_CHECKS[7]
            code, body = http("GET", f"{base}/api/auth/me", token=token)
            if code != 200 or json.loads(body).get("email") != ADMIN_EMAIL:
                fail(name, f"{code} {body[:300]}")
            ok(name)

            name = EXPECTED_CHECKS[8]
            code, body = http("GET", f"{base}/api/marinas", token=token)
            if code != 200:
                fail(name, f"{code} {body[:300]}")
            ok(name)

            name = EXPECTED_CHECKS[9]
            code, body = http("GET", f"{base}/api/auth/me")
            if code != 401:
                fail(name, f"{code} {body[:300]}")
            ok(name)
        finally:
            srv.terminate()
            try:
                srv.wait(timeout=10)
            except subprocess.TimeoutExpired:
                srv.kill()
            log_f.close()

    summary()
    return 0 if _passed == EXPECTED_CHECKS else 1


if __name__ == "__main__":
    sys.exit(main())
