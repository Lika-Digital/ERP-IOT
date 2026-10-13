"""TC-ERP-BOOT-01a / BOOT-02 — the application actually starts.

Not a component test. A real migration on an empty database, a real uvicorn
process, real HTTP: health, the first admin through the one-time link and 2FA
(D20), password + second factor, an authenticated route. Spec §9.

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
# D20.3: a leftover DEFAULT_ADMIN_PASSWORD must seed NOTHING; the check sets one on purpose
LEFTOVER_EMAIL, LEFTOVER_PASSWORD = "seed@check.erp", "leftover-seed-pass"  # noqa: S105
STARTUP_TIMEOUT_S = 40

EXPECTED_CHECKS = [
    "migration: alembic upgrade head on empty database",
    "migration: alembic check - models and migrations agree (O17)",
    "schema: the database itself enforces the spec §4 rules (probes)",
    "negative: without JWT_SECRET the server does not come up",
    "server: uvicorn comes up",
    "GET /api/health -> 200, status ok",
    "D20: DEFAULT_ADMIN_PASSWORD in the environment seeds nobody",
    "D20: first admin - one-time link -> password -> 2FA linked -> full token",
    "D20: password alone -> mfa token only, and it opens nothing (401)",
    "D20: password + backup code -> full token; the same code again -> 401",
    "GET /api/auth/me with token -> 200, same user",
    "GET /api/marinas with token -> 200",
    "GET /api/auth/me without token -> 401",
    "collector: runs, and is the leader (PostgreSQL: advisory lock)",
    "POST /api/webhooks/cabinet/1 without the cabinet's key -> 401",
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
        # drop alembic/uvicorn INFO noise; the reason is at the END, so keep the tail
        lines = [x.strip() for x in detail.splitlines()
                 if x.strip() and not x.lstrip().startswith("INFO")]
        one_line = " | ".join(lines)[-1500:]
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
            "DEFAULT_ADMIN_EMAIL": LEFTOVER_EMAIL,
            "DEFAULT_ADMIN_PASSWORD": LEFTOVER_PASSWORD,
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

            import first_admin

            def post(path, body, bearer):
                code, text = http("POST", f"{base}{path}", body, token=bearer)
                try:
                    return code, json.loads(text)
                except ValueError:
                    return code, text

            name = EXPECTED_CHECKS[6]
            code, body = http("POST", f"{base}/api/auth/login",
                              {"email": LEFTOVER_EMAIL, "password": LEFTOVER_PASSWORD})
            if code != 401:
                fail(name, f"a leftover DEFAULT_ADMIN_PASSWORD signed in: {code} {body[:300]}")
            ok(name)

            name = EXPECTED_CHECKS[7]
            try:
                link = first_admin.link_token(env, ADMIN_EMAIL, cwd=tmp)
                admin = first_admin.enrol(post, link, ADMIN_PASSWORD)
            except RuntimeError as exc:
                fail(name, str(exc))
            ok(name)

            name = EXPECTED_CHECKS[8]
            code, body = post("/api/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                              None)
            mfa = body.get("mfa_token") if code == 200 and isinstance(body, dict) else None
            if not mfa or "access_token" in body:
                fail(name, f"{code} {body}")
            code2, _ = http("GET", f"{base}/api/marinas", token=mfa)
            if code2 != 401:
                fail(name, f"an mfa token opened /api/marinas: {code2}")
            ok(name)

            name = EXPECTED_CHECKS[9]
            backup = admin["backup_codes"][0]
            code, body = post("/api/auth/mfa/verify", {"code": backup}, mfa)
            token = body.get("access_token") if code == 200 and isinstance(body, dict) else None
            if not token:
                fail(name, f"{code} {body}")
            _, again = post("/api/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                            None)
            code, body = post("/api/auth/mfa/verify", {"code": backup}, again["mfa_token"])
            if code != 401:
                fail(name, f"a used backup code worked again: {code} {body}")
            ok(name)

            name = EXPECTED_CHECKS[10]
            code, body = http("GET", f"{base}/api/auth/me", token=token)
            if code != 200 or json.loads(body).get("email") != ADMIN_EMAIL:
                fail(name, f"{code} {body[:300]}")
            ok(name)

            name = EXPECTED_CHECKS[11]
            code, body = http("GET", f"{base}/api/marinas", token=token)
            if code != 200:
                fail(name, f"{code} {body[:300]}")
            ok(name)

            name = EXPECTED_CHECKS[12]
            code, body = http("GET", f"{base}/api/auth/me")
            if code != 401:
                fail(name, f"{code} {body[:300]}")
            ok(name)

            # phase 4: the collector starts with the app (spec §5.2) — not a flag someone
            # has to remember on the VPS
            name = EXPECTED_CHECKS[13]
            deadline = time.monotonic() + 15
            col = {}
            while time.monotonic() < deadline:
                code, body = http("GET", f"{base}/api/health")
                col = json.loads(body).get("collector", {}) if code == 200 else {}
                if col.get("running") and col.get("role") == "leader" and col.get("cycles", 0) >= 1:
                    break
                time.sleep(0.5)
            else:
                fail(name, f"collector state: {col}")
            ok(name)

            name = EXPECTED_CHECKS[14]
            code, body = http("POST", f"{base}/api/webhooks/cabinet/1",
                              {"event": "hardware_alarm", "data": {"id": 1}})
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
