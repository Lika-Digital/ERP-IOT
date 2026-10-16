"""The VPS units in deploy/ (spec §8.1, §8.3, 5b): what must hold in the file itself.

The unit is installed by hand on the VPS, so nothing at runtime would notice if a
later edit put the backend on 0.0.0.0, a secret into the file, or the wrong
database into the URL. These tests do.
"""
import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"


def _unit():
    return (DEPLOY / "erp-iot.service").read_text(encoding="utf-8")


def test_the_backend_listens_on_loopback_only():
    exec_start = next(l for l in _unit().splitlines() if l.startswith("ExecStart="))
    assert "--host 127.0.0.1" in exec_start and "0.0.0.0" not in exec_start
    # the client address is taken from nginx on loopback only (lockout, O43)
    assert "--forwarded-allow-ips 127.0.0.1" in exec_start


def test_secrets_come_from_systemd_credentials_never_from_the_file():
    u = _unit()
    assert "LoadCredential=jwt_secret:/etc/erp-iot/jwt_secret" in u
    assert "LoadCredential=erp_encryption_key:/etc/erp-iot/erp_encryption_key" in u
    for line in u.splitlines():
        if line.startswith(("Environment=", "EnvironmentFile=")):
            assert not re.search(r"JWT_SECRET|ERP_ENCRYPTION_KEY|PASSWORD", line), line


def test_the_database_is_erp_iot_over_the_socket_without_a_password():
    url = re.search(r"DATABASE_URL=(\S+)", _unit()).group(1)
    assert url == "postgresql+psycopg2://erp@/erp_iot?host=/var/run/postgresql"   # §8.3, v25
    run = (DEPLOY / "erp-run").read_text(encoding="utf-8")
    assert url in run


def test_it_runs_as_erp_not_root():
    u = _unit()
    assert "\nUser=erp\n" in u and "\nGroup=erp\n" in u
    assert "NoNewPrivileges=yes" in u and "ProtectSystem=strict" in u


def test_the_manual_runner_hands_over_the_same_secrets_as_the_unit():
    run = (DEPLOY / "erp-run").read_text(encoding="utf-8")
    for cred in ("jwt_secret:/etc/erp-iot/jwt_secret",
                 "erp_encryption_key:/etc/erp-iot/erp_encryption_key"):
        assert f"LoadCredential={cred}" in run
    assert "-p User=erp" in run and 'id -u)" -eq 0' in run


# ── deploy/slusaci.sh (v25.1): javno samo :22, ostalo loopback ili Tailscale ───────────

import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

TS4, TS6 = "100.110.191.12", "fd7a:115c:a1e0::2c34:bf0d"


def _run_slusaci(tmp_path, ss_lines):
    """Run the real script with fake `ss` and `tailscale` first on PATH."""
    fake = tmp_path / "bin"
    fake.mkdir(parents=True)
    rows = "".join(f"LISTEN 0 4096 {a} 0.0.0.0:*\n" for a in ss_lines)
    (fake / "ss").write_text(f"#!/bin/sh\ncat <<'X'\n{rows}X\n", newline="\n")
    (fake / "tailscale").write_text(
        f'#!/bin/sh\n[ "$2" = "-4" ] && echo {TS4} || echo {TS6}\n', newline="\n")
    for f in fake.iterdir():
        f.chmod(0o755)
    bash = shutil.which("bash")
    assert bash, "bash is required for the deploy script tests"
    env = dict(os.environ, PATH=f"{fake.as_posix()}{os.pathsep}{os.environ['PATH']}")
    if os.name == "nt":   # Git Bash: give it a POSIX path in front of its own PATH
        drive, rest = fake.as_posix().split(":", 1)
        env["PATH"] = f"/{drive.lower()}{rest}:/usr/bin:/bin"
    return subprocess.run([bash, (DEPLOY / "slusaci.sh").as_posix()], env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=60)


def test_listeners_tailscale_ipv6_with_zone_is_allowed(tmp_path):
    # the exact line from the VPS, step 5 (2026-10-17): zone after the brackets
    r = _run_slusaci(tmp_path, [f"[{TS6}]%tailscale0:55956",
                                f"{TS4}%tailscale0:49508", "0.0.0.0:22", "[::]:22",
                                "127.0.0.53%lo:53", "127.0.0.54:53"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "GREŠKA" not in r.stdout and "SLUŠAČI: u redu" in r.stdout


def test_listeners_public_port_or_postgres_fails(tmp_path):
    bads = ("0.0.0.0:80", "[::]:8000", "127.0.0.1:5432", "[fd7a::9]%tailscale0:80")
    for i, bad in enumerate(bads):
        r = _run_slusaci(tmp_path / str(i), ["0.0.0.0:22", bad])
        assert r.returncode == 1, (bad, r.stdout)
        assert "SLUŠAČI: GREŠKA" in r.stdout, bad
