"""
Temelji koji ne lazu — faza 1 specifikacije (docs/erp_spec.md §9).

Ovi testovi ne provjeravaju poslovnu logiku. Provjeravaju da repo ne moze
lagati o sebi: da su ovisnosti pinane, da je gate u repou, da autentifikacija
vraca 401, i da se tajna ne izmislja u tisini.

TC-ERP-DEP-01   ovisnosti su pinane i instalirano se slaze s pinovima

Ostali testovi faze 1 dodaju se u istom commitu kao i ponasanje koje tvrde,
da nijedan commit ne ostavi suite crvenim.
"""
from __future__ import annotations

import re
import subprocess
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
