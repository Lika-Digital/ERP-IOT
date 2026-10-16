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
