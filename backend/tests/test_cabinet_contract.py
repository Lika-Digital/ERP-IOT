"""The endpoint table (app/cabinet/contract.py) against spec §2.2 and §2.3.

The spec's table is the decision; the code table is its implementation. This
test parses the spec and compares row by row, so one cannot change without
the other.
"""
import re
from pathlib import Path

import pytest

from app.cabinet import contract as c

_SPEC = Path(__file__).resolve().parents[2] / "docs" / "erp_spec.md"


def _spec_rows():
    text = _SPEC.read_text(encoding="utf-8")
    start = text.index("### §2.2")
    end = text.index("### §2.3")
    rows = {}
    for line in text[start:end].splitlines():
        # the id column may contain an escaped pipe: `PK\|display`
        m = re.match(r"\| `([\w.]+)` \| (GET|POST) \| `([^`]+)` \| ([^|]+) \| ([^|]+) \|", line.replace(r"\|", "/"))
        if m:
            key, method, path, id_type, bidir = (g.strip() for g in m.groups())
            rows[key] = (method, path, id_type.replace("*", "").replace("/", "|"),
                         bidir.replace("*", ""))
    return rows


def test_spec_table_parses():
    assert len(_spec_rows()) == 31          # v21: camera rows gone (D30); P5: push_image_ext


def test_code_table_is_exactly_the_spec_table():
    assert set(c.ENDPOINTS) == set(_spec_rows())


@pytest.mark.parametrize("key", sorted(_spec_rows()))
def test_row_matches_spec(key):
    method, path, id_type, bidir = _spec_rows()[key]
    ep = c.ENDPOINTS[key]
    assert ep.method == method
    # spec uses {id} and {pedestal_id} interchangeably for the pedestal param
    assert ep.path == path.replace("{id}", "{pedestal_id}") or (
        key == "alarms.acknowledge" and ep.path == path.replace("{id}", "{alarm_id}"))
    # The spec's id column is about whatever id the path takes (alarm, session,
    # marina, pedestal). IdType in code is about the PEDESTAL id only, because
    # that is the one with two forms (PK and display_id).
    if "{pedestal_id}" in ep.path:
        expected_id = {"PK": c.IdType.PK, "PK|display": c.IdType.PK_OR_DISPLAY}
        assert ep.id_type is expected_id[id_type], f"{key}: spec says {id_type}"
    else:
        assert ep.id_type is c.IdType.NONE
    assert ep.mode is (c.Mode.BIDIRECTIONAL if bidir == "da" else c.Mode.MONITOR)


def test_path_rule_family_a_replaces_api_with_api_ext():
    assert c.external_path("/api/pedestals/health") == "/api/ext/pedestals/health"


def test_path_rule_family_b_is_verbatim_never_doubled():
    p = "/api/ext/pedestals/{pedestal_id}/load"
    assert c.external_path(p) == p
    for ep in c.ENDPOINTS.values():
        assert "/api/ext/ext/" not in ep.path


def test_family_b_has_17_routes_of_which_the_erp_uses_13():
    # 17 direct routes on the cabinet (NALAZ 1.1); 2 are never enabled (§2.3):
    # breakers.socket_reset_ext, load.auto_stop_ack_ext; since v21 (D30) the ERP calls
    # neither camera route (frame, stream); since P5 berths.push_image_ext is in, per
    # cabinet with the P1 record
    fam_b = [e for e in c.ENDPOINTS.values() if e.catalog_path.startswith("/api/ext/")]
    assert len(fam_b) == 13


def test_never_enabled_keys_are_not_callable():
    assert not (c.NEVER_ENABLE & set(c.ENDPOINTS))
    for key in c.NEVER_ENABLE:
        with pytest.raises(c.ContractError):
            c.build_path(key)


def test_display_id_on_pk_route_is_refused_before_sending():
    with pytest.raises(c.ContractError, match="NALAZ 3.1"):
        c.build_path("load.pedestal_get_ext", pedestal_id="MAR_KRK_ORM_01")
    assert c.build_path("load.pedestal_get_ext", pedestal_id=7) == "/api/ext/pedestals/7/load"


def test_display_id_allowed_where_the_cabinet_resolves_it():
    assert c.build_path("pedestals.status_ext", pedestal_id="MAR_KRK_ORM_01") == \
        "/api/ext/pedestals/MAR_KRK_ORM_01/status"


@pytest.mark.parametrize("bad", ["1", 1, "Q5", "socket1"])
def test_outlet_names_are_prefixed_strings(bad):
    with pytest.raises(c.ContractError):
        c.build_path("controls.socket_cmd", pedestal_id=1, socket_name=bad)


def test_missing_or_extra_params_are_refused():
    with pytest.raises(c.ContractError):
        c.build_path("controls.allow")
    with pytest.raises(c.ContractError):
        c.build_path("pedestals.health", pedestal_id=1)


def test_reverse_lookup():
    assert c.endpoint_for("GET", "/api/ext/pedestals/7/load").key == "load.pedestal_get_ext"
    assert c.endpoint_for("GET", "/api/ext/ext/pedestals/7/load") is None


def test_no_cabinet_path_is_built_outside_the_contract_module():
    """§2.1: nothing else builds a cabinet URL. Scan app/ for /api/ext literals."""
    app = Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for f in app.rglob("*.py"):
        if f.name == "contract.py" or "__pycache__" in f.parts:
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"""["']/api/(ext|nfc)/""", line):
                # D21 layer 2: the ERP's OWN decoy route mirrors the gateway's decoy
                # path — an inbound path that no client ever calls on a cabinet
                if f.name == "decoys.py" and '"/api/ext/admin/debug"' in line:
                    continue
                offenders.append(f"{f.relative_to(app)}:{i}")
    assert offenders == []
