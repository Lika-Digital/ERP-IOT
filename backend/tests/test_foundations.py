"""
Temelji koji ne lazu — faza 1 specifikacije (docs/erp_spec.md §9).

Ovi testovi ne provjeravaju poslovnu logiku. Provjeravaju da repo ne moze
lagati o sebi: da su ovisnosti pinane, da je gate u repou, da autentifikacija
vraca 401, i da se tajna ne izmislja u tisini.

TC-ERP-DEP-01   ovisnosti su pinane i instalirano se slaze s pinovima
TC-ERP-AUTH-01  neautentificirano = strogo 401 na svakoj zasticenoj ruti
TC-ERP-AUTH-02  JWT_SECRET koji fali ili je prazan zaustavlja podizanje
TC-ERP-CACHE-01 kes API odgovora prezivi restart (cache_key stupac, ne hash)
TC-ERP-GATE-01  gate je u repou: .githooks + core.hooksPath, CI vrti isti skript
TC-ERP-BOOT-02  gate ne moze proci prazno (boot pada glasno, preskoceni test je pad)
(TC-ERP-BOOT-01a sam je scripts/boot_check.py — pravi uvicorn, vrti ga gate)

Ostali testovi faze 1 dodaju se u istom commitu kao i ponasanje koje tvrde,
da nijedan commit ne ostavi suite crvenim.
"""
from __future__ import annotations

import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
_REPO = _BACKEND.parent

_REQ = _BACKEND / "requirements.txt"
_LOCK = _BACKEND / "requirements.lock"

_PIN_RE = re.compile(r"^(?P<name>[A-Za-z0-9._-]+)(?P<extras>\[[^\]]+\])?==(?P<version>.+)$")


def _pin_lines(path: Path) -> list[str]:
    return [
        ln.strip()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]


# ─── TC-ERP-DEP-01 ────────────────────────────────────────────────────────────

def test_tc_erp_dep_01_requirements_exist():
    assert _REQ.is_file(), "backend/requirements.txt mora postojati"
    assert _LOCK.is_file(), (
        "backend/requirements.lock mora postojati — bez njega instalacija nije "
        "ponovljiva, a to je cijeli razlog faze 1 (spec §0.1)"
    )


def test_tc_erp_dep_01_every_direct_dependency_is_pinned():
    """Nijedna direktna ovisnost ne smije biti bez ==.

    Spec §0.1: ponasanje HTTPBearer-a promijenilo se iz 403 u 401 bez ijednog
    commita, jer je requirements.txt pinao samo bcrypt. Ovaj test je ono sto
    sprjecava da se to ponovi.
    """
    unpinned = [ln for ln in _pin_lines(_REQ) if not _PIN_RE.match(ln)]
    assert not unpinned, f"nepinane direktne ovisnosti: {unpinned}"


def test_tc_erp_dep_01_lock_is_not_smaller_than_direct_set():
    direct = {_PIN_RE.match(ln).group("name").lower() for ln in _pin_lines(_REQ)}
    locked = {_PIN_RE.match(ln).group("name").lower()
              for ln in _pin_lines(_LOCK) if _PIN_RE.match(ln)}
    missing = sorted(direct - locked)
    assert not missing, (
        f"requirements.lock ne sadrzi direktne ovisnosti: {missing} — "
        "lock je generiran iz drugog okruzenja"
    )


def test_tc_erp_dep_01_installed_matches_pins():
    """Instalirano okruzenje mora odgovarati pinovima.

    Ako ne odgovara, gate mjeri nesto drugo od onoga sto se deployira.
    """
    drift = []
    for ln in _pin_lines(_REQ):
        m = _PIN_RE.match(ln)
        name, want = m.group("name"), m.group("version")
        try:
            have = metadata.version(name)
        except metadata.PackageNotFoundError:
            drift.append(f"{name}: pinan {want}, NIJE INSTALIRAN")
            continue
        if have != want:
            drift.append(f"{name}: pinan {want}, instaliran {have}")
    assert not drift, "okruzenje se razilazi od pinova:\n  " + "\n  ".join(drift)


def test_tc_erp_dep_01_bcrypt_pin_is_load_bearing():
    """bcrypt < 4.1 je uvjet da passlib radi (spec §11 O1).

    Ovaj test postoji da se pin ne 'ocisti' pri rutinskom azuriranju. Ako
    passlib ikad bude zamijenjen, test se brise u istom commitu — ne prije.
    """
    assert metadata.version("passlib").startswith("1.7"), "passlib verzija se promijenila"
    major, minor = (int(x) for x in metadata.version("bcrypt").split(".")[:2])
    assert (major, minor) < (4, 1), (
        f"bcrypt {major}.{minor} s passlib 1.7.x ne radi — passlib cita bcrypt.__about__, "
        "koji je uklonjen u 4.1. Vidi spec §11 O1."
    )


def test_tc_erp_dep_01_tooling_is_in_the_venv_not_global():
    """bandit i ruff moraju biti ovisnosti projekta.

    Nalaz faze 1: oboje je bilo instalirano samo globalno, pa je gate prolazio
    na stroju autora i preskocio bi na cistom VPS-u.
    """
    for tool in ("bandit", "ruff"):
        try:
            metadata.version(tool)
        except metadata.PackageNotFoundError:
            pytest.fail(f"{tool} nije instaliran u okruzenju projekta, samo globalno")


def test_tc_erp_dep_01_frontend_lock_is_tracked():
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "frontend/package-lock.json"],
        cwd=_REPO, capture_output=True, text=True,
    )
    assert tracked.returncode == 0, (
        "frontend/package-lock.json nije u gitu — npm install tada moze "
        "rijesiti druge verzije od onih koje smo testirali (spec §11 O4)"
    )


# ─── TC-ERP-AUTH-02 ───────────────────────────────────────────────────────────

def _import_config_with(env: dict) -> subprocess.CompletedProcess:
    """Uvezi app.config u svjezem procesu, IZOLIRANO od backend/.env.

    Proces se vrti iz privremenog direktorija s PYTHONPATH na backend, pa
    pydantic-settings ne nalazi `.env`. Bez te izolacije test ne bi mjerio
    fail-fast nego postojanje razvojne datoteke na ovom stroju.
    """
    import os
    import tempfile

    e = dict(os.environ)
    e["PYTHONPATH"] = str(_BACKEND)
    e["DATABASE_URL"] = "sqlite:///./_authcheck.db"
    for k, v in env.items():
        if v is None:
            e.pop(k, None)
        else:
            e[k] = v
    with tempfile.TemporaryDirectory() as tmp:
        return subprocess.run(
            [sys.executable, "-c", "import app.config"],
            cwd=tmp, capture_output=True, text=True, env=e,
        )

def test_tc_erp_auth_02_absent_jwt_secret_refuses_to_boot():
    """Bez JWT_SECRET aplikacija se NE SMIJE dici.

    Prije faze 1 generirala se slucajna tajna i upisao CRITICAL u log. Posljedica:
    svaki restart nevaljanim cini sve sesije, a log nitko ne gleda. Tiha
    degradacija sigurnosti je gora od odbijenog podizanja (spec §7.1).
    """
    proc = _import_config_with({"JWT_SECRET": None})
    assert proc.returncode != 0, (
        "app.config se uvezao bez JWT_SECRET — fail-fast ne radi. "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "JWT_SECRET" in proc.stdout + proc.stderr, (
        "podizanje je palo, ali poruka ne imenuje JWT_SECRET — greska mora reci sto fali"
    )


def test_tc_erp_auth_02_blank_jwt_secret_also_refuses_to_boot():
    """Prazan string je takoder 'nije postavljeno'.

    `.env.example` nosi `JWT_SECRET=` s praznom vrijednoscu (spec §8.3), pa bi
    provjera samo na None propustila tocno onaj slucaj zbog kojeg postoji:
    nekoga ko je kopirao primjer i nije ga popunio.
    """
    for blank in ("", "   "):
        proc = _import_config_with({"JWT_SECRET": blank})
        assert proc.returncode != 0, f"prazan JWT_SECRET ({blank!r}) je prosao"


def test_tc_erp_auth_02_present_jwt_secret_boots():
    """Pozitivna strana: s tajnom se config uvozi normalno.

    Bez ovoga bi test gore prosao i da config puca uvijek.
    """
    proc = _import_config_with({"JWT_SECRET": "x" * 64})
    assert proc.returncode == 0, f"config ne uvozi ni s tajnom: {proc.stderr!r}"


def test_tc_erp_auth_02_env_example_ships_blank_secrets():
    """Primjeri tajni moraju biti PRAZNI, ne 'change-me'.

    'change-me-in-production' je gore od prazne vrijednosti: s njom se
    aplikacija digne, pa fail-fast nikad ne okine i tajna iz primjera ode u
    produkciju.
    """
    body = (_BACKEND / ".env.example").read_text(encoding="utf-8")
    for key in ("DATABASE_URL", "JWT_SECRET", "DEFAULT_ADMIN_PASSWORD", "ERP_ENCRYPTION_KEY"):
        assert re.search(rf"^{key}=\s*$", body, re.M), (
            f"{key} u .env.example nema praznu vrijednost (spec §8.3)"
        )
    assert "change-me" not in body, ".env.example jos nosi 'change-me' vrijednost"


def test_o16_absent_database_url_refuses_to_boot():
    """Bez DATABASE_URL nema podizanja — ni tihog pada na zadani URL s lozinkom."""
    proc = _import_config_with({"JWT_SECRET": "x" * 64, "DATABASE_URL": None})
    assert proc.returncode != 0
    assert "DATABASE_URL" in proc.stderr


# <lozinka> u komentaru je oznaka mjesta, ne lozinka
_CRED_URL = re.compile(r"\w+://[^\s:/@]+:(?!<)[^\s@]+@")


def test_o16_no_database_credentials_in_config_files():
    """URL s korisnikom i lozinkom ne smije biti u datotekama koje se citaju.

    alembic.ini je nosio javnu lozinku (spec §11 O16), config.py zadani URL s
    drugom. Oboje su sad bez lozinke; jedini izvor je DATABASE_URL.
    """
    for rel in ("alembic.ini", ".env.example", "app/config.py", "alembic/env.py"):
        text = (_BACKEND / rel).read_text(encoding="utf-8")
        hit = _CRED_URL.search(text)
        assert not hit, f"{rel}: URL s lozinkom ({hit.group(0)[:30]}…)"


def test_tc_erp_auth_02_app_does_not_bind_all_interfaces_by_default():
    """Spec §8.1: nginx je jedini javni slusatelj.

    B104 je bio jedini medium nalaz bandita u repou.
    """
    import os
    os.environ.setdefault("JWT_SECRET", "test-secret-for-erp-iot-ci")
    from app.config import Settings

    assert Settings().app_host == "127.0.0.1", (
        "app_host default je 0.0.0.0 — prvo pogresno pravilo vatrozida izlozilo bi "
        "backend izravno (spec §8.1)"
    )


# ─── TC-ERP-AUTH-01 ───────────────────────────────────────────────────────────
#
# Popis ruta se NE pise rukom i ne broji grepom. Grep po
# `Depends(get_current_user)` daje 23 (spec §9 v3), ali promasuje rute koje su
# zasticene kroz require_super_admin / require_any_operator — stvarni graf
# ovisnosti ima 27 od 31. Rucni popis bi zastario s prvom novom rutom; graf ne.

_PUBLIC_ROUTES = {
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/refresh"),
    ("POST", "/api/webhooks/pedestal/{marina_id}"),  # vlastita provjera X-API-Key
    ("GET", "/api/health"),
}


def _route_calls(dependant):
    for sub in dependant.dependencies:
        yield sub.call
        yield from _route_calls(sub)


def _routes():
    from fastapi.routing import APIRoute
    from app.main import app
    from app.routers.auth import get_current_user

    out = []
    for r in app.routes:
        if not isinstance(r, APIRoute):
            continue
        protected = get_current_user in set(_route_calls(r.dependant))
        for m in sorted(r.methods):
            out.append((m, r.path, protected))
    return out


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


def test_tc_erp_auth_01_public_set_is_exactly_known():
    """Svaka ruta bez get_current_user mora biti ovdje navedena po imenu.

    Nova ruta koja zaboravi autentifikaciju ne smije proci tiho kao "javna" —
    pada ovdje, i netko mora svjesno dopisati je u _PUBLIC_ROUTES.
    """
    public = {(m, p) for m, p, prot in _routes() if not prot}
    assert public == _PUBLIC_ROUTES


def test_tc_erp_auth_01_protected_count_matches_graph():
    """27 zasticenih od 31 — izmjereno iz grafa ovisnosti, ne grepom."""
    rs = _routes()
    assert (sum(p for _, _, p in rs), len(rs)) == (27, 31)


def test_tc_erp_auth_01_no_credentials_is_strictly_401(client):
    """Bez Authorization zaglavlja: strogo 401 na SVAKOJ zasticenoj ruti.

    Ne `in (401, 403)`. Upravo je ta tolerancija sakrila da se ponasanje
    HTTPBearera promijenilo pod repoom bez ijednog commita (spec §0.1).
    """
    wrong = []
    for m, p, prot in _routes():
        if prot:
            code = client.request(m, _concrete(p)).status_code
            if code != 401:
                wrong.append((m, p, code))
    assert wrong == []


def test_tc_erp_auth_01_garbage_token_is_strictly_401(client):
    """Neispravan token je isto 'ne znamo ko si' — 401, ne 403 ni 422."""
    h = {"Authorization": "Bearer not-a-jwt"}
    wrong = []
    for m, p, prot in _routes():
        if prot:
            code = client.request(m, _concrete(p), headers=h).status_code
            if code != 401:
                wrong.append((m, p, code))
    assert wrong == []


# ─── TC-ERP-CACHE-01 ──────────────────────────────────────────────────────────
#
# Restart se simulira kao sto se stvarno dogada: novi proces s DRUGIM
# PYTHONHASHSEED. U istom procesu hash(str) je stabilan, pa test unutar jednog
# procesa ne bi mogao uhvatiti stari bug.

_CACHE_SCRIPT = r"""
import sys
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import marina, user, cache  # noqa: F401
from app.models.cache import PedestalCache
from app.services.pedestal_api import _update_cache, _get_cache

engine = create_engine(sys.argv[1])
Base.metadata.create_all(bind=engine)
db = sessionmaker(bind=engine)()
if sys.argv[2] == "write":
    _update_cache(db, 1, "list_pedestals", {"writer": sys.argv[3]})
else:
    print(_get_cache(db, 1, "list_pedestals"))
print("ROWS", db.query(func.count(PedestalCache.id)).scalar())
"""


def _cache_proc(db_url: str, seed: str, *args: str) -> str:
    import os

    e = dict(os.environ)
    e.update({
        "PYTHONPATH": str(_BACKEND),
        "PYTHONHASHSEED": seed,
        "DATABASE_URL": db_url,
        "JWT_SECRET": "cache-test",
        "DEFAULT_ADMIN_PASSWORD": "cache-test",
        "ERP_ENCRYPTION_KEY": "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=",
    })
    r = subprocess.run(
        [sys.executable, "-c", _CACHE_SCRIPT, db_url, *args],
        cwd=str(_BACKEND), capture_output=True, text=True, env=e,
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_tc_erp_cache_01_cache_survives_restart(tmp_path):
    """Dva procesa, razliciti hash seed, isti kljuc -> isti redak.

    Prije faze 1 kljuc je bio abs(hash(cache_key)) % 10**9: drugi proces
    nije nalazio redak prvoga, stale fallback je tiho vracao None, a stari
    redak je ostajao siroce (spec §4.8).
    """
    url = f"sqlite:///{tmp_path / 'cache.db'}"
    out_a = _cache_proc(url, "1", "write", "A")
    assert "ROWS 1" in out_a

    out_b = _cache_proc(url, "2", "read")
    assert "{'writer': 'A'}" in out_b, "drugi proces ne vidi kes prvoga"

    out_c = _cache_proc(url, "3", "write", "C")
    assert "ROWS 1" in out_c, "restart je stvorio novi redak umjesto azuriranja"


def test_tc_erp_cache_01_key_is_a_column_with_unique_constraint():
    from app.models.cache import PedestalCache

    t = PedestalCache.__table__
    assert "cache_key" in t.c
    uniques = {
        tuple(c.name for c in con.columns)
        for con in t.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    }
    assert ("marina_id", "cache_key") in uniques


def test_tc_erp_cache_01_migration_drops_hash_rows_keeps_readings(tmp_path):
    """Migracija 005 na pravoj bazi s redcima kakve je stari kod ostavio."""
    import os
    import sqlite3

    db = tmp_path / "mig.db"
    e = dict(os.environ)
    e.update({
        "DATABASE_URL": f"sqlite:///{db}",
        "JWT_SECRET": "mig-test",
        "DEFAULT_ADMIN_PASSWORD": "mig-test",
    })

    def alembic(*a):
        r = subprocess.run(
            [sys.executable, "-m", "alembic", *a],
            cwd=str(_BACKEND), capture_output=True, text=True, env=e,
        )
        assert r.returncode == 0, r.stderr

    alembic("upgrade", "004")
    con = sqlite3.connect(db)
    # SQLite ne provodi FK bez PRAGMA, pa marina 1 ne mora postojati
    # hash-keyed API cache row, as the old code wrote it
    con.execute("INSERT INTO pedestal_cache (marina_id, pedestal_id, last_seen_data, is_stale) "
                "VALUES (1, 734512901, '{}', 0)")
    # webhook row with readings, real pedestal id
    con.execute("INSERT INTO pedestal_cache (marina_id, pedestal_id, last_readings, is_stale) "
                "VALUES (1, 3, '{\"heartbeat\": {}}', 0)")
    con.commit()
    con.close()

    alembic("upgrade", "head")
    con = sqlite3.connect(db)
    rows = con.execute("SELECT pedestal_id, cache_key FROM pedestal_cache").fetchall()
    con.close()
    assert rows == [(3, None)]


# ─── Uklonjeni poziv koji cilja nepostojecu rutu (spec §4.8) ─────────────────

def test_no_call_to_nonexistent_camera_detections_route():
    """/api/ext/camera/{id}/detections ne postoji na ormaru i nije u katalogu.

    Metoda koja je zove imala je nula pozivatelja. Ostavljena, prvi bi je
    netko pozvao i dobio 404 kao "ormar ne radi".
    """
    from app.services.pedestal_api import PedestalAPIClient

    assert not hasattr(PedestalAPIClient, "get_camera_detections")
    src = (_BACKEND / "app" / "services" / "pedestal_api.py").read_text(encoding="utf-8")
    assert "/detections" not in src


# ─── TC-ERP-GATE-01 ───────────────────────────────────────────────────────────

def test_tc_erp_gate_01_hooks_are_versioned_and_call_the_gate():
    for hook, arg in (("pre-commit", "--fast"), ("pre-push", "")):
        p = _REPO / ".githooks" / hook
        assert p.is_file(), f".githooks/{hook} ne postoji — gate bi bio samo lokalan"
        text = p.read_text(encoding="utf-8")
        assert "scripts/gate.sh" in text
        if arg:
            assert arg in text


def test_tc_erp_gate_01_ci_runs_the_same_script():
    wf = _REPO / ".github" / "workflows" / "gate.yml"
    assert wf.is_file(), "CI workflow ne postoji"
    text = wf.read_text(encoding="utf-8")
    assert "bash scripts/gate.sh" in text
    assert "requirements.lock" in text, "CI mora instalirati iz locka, ne iz requirements.txt"
    assert "npm ci" in text, "CI mora instalirati frontend iz package-lock.json"


def test_tc_erp_gate_01_hooks_path_is_set_or_this_is_ci():
    """Lokalno core.hooksPath mora pokazivati na .githooks.

    U CI-ju hookovi ne postoje kao pojam — tamo isti skript vrti workflow, sto
    gornji test tvrdi. Ovo nije preskakanje: u CI-ju se tvrdi workflow, lokalno
    oboje.
    """
    import os

    if os.environ.get("CI") == "true":
        assert (_REPO / ".github" / "workflows" / "gate.yml").is_file()
        return
    r = subprocess.run(["git", "config", "core.hooksPath"],
                       cwd=_REPO, capture_output=True, text=True)
    assert r.stdout.strip() == ".githooks", (
        "core.hooksPath nije postavljen — pokreni: git config core.hooksPath .githooks"
    )


def test_tc_erp_gate_01_hooks_are_executable_in_git():
    r = subprocess.run(["git", "ls-files", "-s", ".githooks"],
                       cwd=_REPO, capture_output=True, text=True)
    modes = {ln.split()[3]: ln.split()[0] for ln in r.stdout.splitlines()}
    assert modes.get(".githooks/pre-commit") == "100755"
    assert modes.get(".githooks/pre-push") == "100755"


# ─── TC-ERP-BOOT-02 ───────────────────────────────────────────────────────────

def test_tc_erp_boot_02_boot_check_fails_loudly_when_nothing_comes_up():
    """Baza koja ne postoji -> migracija pada -> boot_check NIKAD ne izlazi s 0."""
    import os

    e = dict(os.environ)
    e["BOOT_DATABASE_URL"] = "postgresql://nobody:x@127.0.0.1:1/none"
    r = subprocess.run(
        [sys.executable, str(_REPO / "scripts" / "boot_check.py")],
        capture_output=True, text=True, env=e, timeout=120,
    )
    assert r.returncode != 0
    assert "BOOT: 0/8 checks passed" in r.stdout


def _junit(tmp_path, tests: int, skipped: int, failures: int = 0) -> Path:
    cases = "".join(
        f'<testcase classname="t" name="c{i}">'
        + ('<skipped message="backend not up"/>' if i < skipped else "")
        + "</testcase>"
        for i in range(tests)
    )
    p = tmp_path / "junit.xml"
    p.write_text(
        f'<testsuites><testsuite tests="{tests}" skipped="{skipped}" '
        f'failures="{failures}" errors="0">{cases}</testsuite></testsuites>',
        encoding="utf-8",
    )
    return p


def _counts(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_REPO / "scripts" / "pytest_counts.py"), str(path)],
        capture_output=True, text=True,
    )


def test_tc_erp_boot_02_skipped_test_fails_the_gate(tmp_path):
    r = _counts(_junit(tmp_path, tests=5, skipped=1))
    assert r.returncode != 0
    assert "skipped=1" in r.stdout
    assert "t::c0" in r.stdout, "preskoceni test mora biti imenovan"


def test_tc_erp_boot_02_empty_run_fails_the_gate(tmp_path):
    r = _counts(_junit(tmp_path, tests=0, skipped=0))
    assert r.returncode != 0
    assert "collected=0" in r.stdout


def test_tc_erp_boot_02_missing_report_fails_the_gate(tmp_path):
    assert _counts(tmp_path / "nope.xml").returncode != 0


def test_tc_erp_boot_02_clean_run_passes(tmp_path):
    r = _counts(_junit(tmp_path, tests=3, skipped=0))
    assert r.returncode == 0, r.stdout


def test_tc_erp_boot_02_gate_has_no_soft_fallbacks():
    """Stari run_tests.sh: sistemski Python, pip install bez pina, bandit 'skipping'."""
    assert not (_REPO / "tests" / "run_tests.sh").exists()
    gate = (_REPO / "scripts" / "gate.sh").read_text(encoding="utf-8")
    # jedini dopusteni "pip install" je uputa za instalaciju IZ locka
    assert not re.search(r"pip install(?! -r backend/requirements\.lock)", gate)
    assert "skipping" not in gate.lower()
    assert "command -v python" not in gate, "gate ne smije pasti na sistemski Python"


# ─── O18: jedan sat, bez datetime.utcnow ─────────────────────────────────────

def test_o18_utcnow_is_naive_utc_like_the_columns():
    """Stupci su naivni i drze UTC; utcnow() mora vratiti tocno taj oblik.

    Svjestan (aware) datetime usporeden s naivnim iz baze baca TypeError — zato
    pomocnik NIJE samo datetime.now(timezone.utc).
    """
    from datetime import datetime, timezone

    from app.utils.time import utcnow

    t = utcnow()
    assert t.tzinfo is None
    ref = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((ref - t).total_seconds()) < 5


def test_o18_ruff_enforces_dtz():
    """DTZ je u pinanim pravilima — novi datetime.utcnow() ruši lint stage."""
    text = (_BACKEND / "ruff.toml").read_text(encoding="utf-8")
    assert re.search(r'^select = \[.*"DTZ".*\]', text, re.M)
