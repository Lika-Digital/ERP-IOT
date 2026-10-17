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
    # encrypted at rest with systemd-creds (5b step 7); a plain LoadCredential= would
    # read a cleartext file
    assert "LoadCredentialEncrypted=jwt_secret:/etc/erp-iot/jwt_secret.cred" in u
    assert "LoadCredentialEncrypted=erp_encryption_key:/etc/erp-iot/erp_encryption_key.cred" in u
    assert not re.search(r"^LoadCredential=", u, re.M)
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
    for cred in ("jwt_secret:/etc/erp-iot/jwt_secret.cred",
                 "erp_encryption_key:/etc/erp-iot/erp_encryption_key.cred"):
        assert f"LoadCredentialEncrypted={cred}" in run
    assert "-p LoadCredential=" not in run
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


# ── deploy/08_blok_a.sh (koraci 8–10): skripta traži točno ono što kod piše ─────────────

def test_block_a_waits_for_the_texts_the_code_really_writes():
    blok = (DEPLOY / "08_blok_a.sh").read_text(encoding="utf-8")
    root = DEPLOY.parent / "backend"
    # P3: start na bazi ispod head mora pasti s ovom porukom (app/database.py)
    assert "P3_MSG='run `alembic upgrade head`'" in blok
    assert "— run `alembic upgrade head`" in (root / "app" / "database.py").read_text(encoding="utf-8")
    # jedan prolaz agenta: logger "erp-agent", poruka "pass ..." (app/agent/__main__.py)
    agent = (root / "app" / "agent" / "__main__.py").read_text(encoding="utf-8")
    assert "'erp-agent: pass '" in blok
    assert 'getLogger("erp-agent")' in agent and 'log.info("pass %s"' in agent
    assert '%(name)s: %(message)s' in agent
    # head u runbooku = head u kodu
    head = re.search(r"^HEAD_REV=(\d+)", blok, re.M).group(1)
    versions = sorted(p.name for p in (root / "alembic" / "versions").glob("[0-9]*.py"))
    assert versions[-1].startswith(head + "_")
    # P3 (downgrade) samo na bazi bez korisnika
    assert re.search(r'if \[ "\$users" != 0 \]', blok)
    # greška izvan pokreni() javi se sa STANI (i uputom za vraćanje s 014); poslije namjernog
    # pada u P3 start-limit se poništi prije starta na head
    assert "set -Eeuo pipefail" in blok and "trap 'stani" in blok
    assert blok.index("reset-failed erp-iot") < blok.index("sudo systemctl restart erp-iot")


# ── deploy/kljucevi_repo.sh: privatni repo, deploy ključevi samo za čitanje ─────────────

def test_deploy_keys_print_only_public_halves_and_pin_github():
    s = (DEPLOY / "kljucevi_repo.sh").read_text(encoding="utf-8")
    # svaki ispis ključa (cat/sed) ide na .pub; privatni dio nikad ne izlazi
    for line in s.splitlines():
        if re.search(r"\b(cat|sed)\b.*\$(L|R)_KEY", line):
            assert "_KEY.pub" in line, line
    # GitHubov ključ poslužitelja: objavljeni ed25519 otisak, strogo
    assert "GH_FP='SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU'" in s
    assert "StrictHostKeyChecking=yes" in s and "IdentitiesOnly=yes" in s
    # ključ koji smije pisati je greška
    assert "push --dry-run" in s and "SMIJE pisati" in s
    # korak 6 klonira /opt/erp-iot istim root ključem
    six = (DEPLOY / "06_aplikacija.sh").read_text(encoding="utf-8")
    assert "REPO=git@github.com:Lika-Digital/ERP-IOT.git" in six
    assert "-i /root/.ssh/erp_iot_deploy -o IdentitiesOnly=yes " \
           "-o UserKnownHostsFile=/root/.ssh/known_hosts_github" in six


# ── blok B: nginx samo na Tailscale IP-u, dist s grane dist (koraci 11, 12) ─────────────

def test_nginx_listens_only_on_the_tailscale_address_and_hides_the_webhook():
    conf = (DEPLOY / "nginx-erp-iot.conf").read_text(encoding="utf-8")
    listens = re.findall(r"^\s*listen\s+([^;]+);", conf, re.M)
    assert listens == ["@TS_IP@:80"]                      # ni 0.0.0.0, ni [::], ni :8081
    assert re.search(r"location \^~ /api/webhooks/ \{\s*return 404;", conf)
    # O43: ograničenje po IP-u baš na rutama prijave
    assert "limit_req_zone $binary_remote_addr zone=erp_prijava" in conf
    assert re.search(r"location ~ \^/api/auth/\(login\|mfa/verify\|setup\|setup/check\)\$ \{\s*"
                     r"limit_req zone=erp_prijava", conf)
    # adresa klijenta se postavlja (uvicorn joj vjeruje s 127.0.0.1), nikad nadovezuje
    assert "$proxy_add_x_forwarded_for" not in conf
    assert conf.count("proxy_set_header X-Forwarded-For $remote_addr;") == 3
    assert set(re.findall(r"proxy_pass\s+([^;]+);", conf)) == {"http://127.0.0.1:8000"}
    dropin = (DEPLOY / "nginx-tailscale.conf").read_text(encoding="utf-8")
    assert "After=tailscaled.service" in dropin and 'inet @TS_IP@/' in dropin


def test_dist_is_published_by_one_writing_job_and_checked_before_unpacking():
    gate = (DEPLOY.parent / ".github" / "workflows" / "gate.yml").read_text(encoding="utf-8")
    head, publish = gate.split("\n  publish-dist:\n")
    assert "contents: write" not in head                  # gate (npm, testovi) ne piše
    assert "contents: write" in publish and "needs: gate" in publish
    assert "npm" not in publish
    assert "frontend_tree=$(git rev-parse HEAD:frontend)" in head
    b = (DEPLOY / "11_blok_b.sh").read_text(encoding="utf-8")
    assert "rev-parse HEAD:frontend" in b and "sha256sum -c" in b
    assert b.index("sha256sum -c") < b.index("tar -xzf")
    assert b.index("u taru je link ili uređaj") < b.index("tar -xzf")
    # apt ne smije pokrenuti zadani site na 0.0.0.0:80
    assert b.index("policy-rc.d") < b.index("apt-get install -y -qq nginx")
    assert "rm -f /etc/nginx/sites-enabled/default" in b
