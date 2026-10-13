"""Phase 3 — the model in use: provisioning, the mapping (D1, D18), NFC import for
Krk (D6.1), the credit ledger (D9). The database-level rules are in
test_model_rules.py; here is the behaviour on top of them.

End-of-phase criterion (§10): importing the Krk CSV hits the EXACT outlet,
not just "recognised" — test_krk_csv_import_hits_the_exact_outlet.
"""
import re
from decimal import Decimal
from pathlib import Path

import pytest

from app.cabinet.nfc_uid import both_forms
from app.services import cabinets as svc
from app.services import credit, nfc_tags

_ODLUKE = Path(__file__).resolve().parents[2] / "docs" / "inputs" / "odluke.md"


@pytest.fixture
def db(setup_test_database, marina_id):
    from tests.conftest import TestSession, _clear_cabinets
    _clear_cabinets(marina_id)
    s = TestSession()
    yield s
    s.rollback()
    s.close()
    _clear_cabinets(marina_id)


def _krk(db, marina_id, device_type="full"):
    return svc.provision_cabinet(
        db, marina_id=marina_id, pedestal_pk=1, display_id="MAR_KRK_ORM_01",
        device_type=device_type, base_url="http://x", service_email="e@x",
        service_password="p")


def _d61_table():
    """The Krk tag table, read from D6.1 itself — the test cannot drift from the decision."""
    text = _ODLUKE.read_text(encoding="utf-8")
    sect = text[text.index("### D6.1"):text.index("## D7")]
    rows = re.findall(r"^\| (Q[1-4]|V[12]) \| [^|]+ \| ([0-9A-F:]{23}) \| ([0-9A-F:]{23}) \|",
                      sect, re.M)
    assert len(rows) == 6, rows
    return rows


def _csv(rows):
    return "outlet,uid,uid_reversed\n" + "\n".join(f"{o},{u},{r}" for o, u, r in rows)


# ─── provisioning (D3) ───────────────────────────────────────────────────────

def test_full_cabinet_has_six_named_outlets_and_q1_is_three_phase(db, marina_id):
    from app.models.cabinet import Outlet
    cab = _krk(db, marina_id)
    outs = {o.outlet_name: o for o in db.query(Outlet).filter(Outlet.cabinet_id == cab.id)}
    assert sorted(outs) == ["Q1", "Q2", "Q3", "Q4", "V1", "V2"]
    assert (outs["Q1"].phases, outs["Q1"].rated_amps) == (3, 32)
    assert (outs["Q3"].phases, outs["Q3"].rated_amps) == (1, 16)
    assert outs["V1"].rated_lpm == 20 and outs["V1"].phases is None


def test_retrofit_has_no_water_outlet_and_says_so(db, marina_id):
    from app.models.cabinet import CabinetCapability, Outlet
    cab = _krk(db, marina_id, "retrofit")
    names = {o.outlet_name for o in db.query(Outlet).filter(Outlet.cabinet_id == cab.id)}
    assert names == {"Q1", "Q2", "Q3", "Q4"}
    caps = {c.capability: c.available for c in
            db.query(CabinetCapability).filter(CabinetCapability.cabinet_id == cab.id)}
    assert caps["water"] is False and caps["power"] is True


def test_service_password_is_stored_encrypted(db, marina_id):
    from app.utils.encryption import decrypt_password
    cab = _krk(db, marina_id)
    assert cab.service_pw_enc != "p" and decrypt_password(cab.service_pw_enc) == "p"


# ─── mapping (D1, D18) ───────────────────────────────────────────────────────

def _berth(db, marina_id, cab, n):
    return svc.create_berth(db, marina_id=marina_id, berth_number=f"A-{n:02d}",
                            cabinet_id=cab.id, cabinet_berth_id=n)


@pytest.mark.parametrize("actor", [None, "", "   "])
def test_mapping_without_an_actor_is_refused(db, marina_id, actor):
    cab = _krk(db, marina_id)
    b = _berth(db, marina_id, cab, 1)
    with pytest.raises(svc.DomainError, match="actor"):
        svc.set_berth_outlets(db, b, ["Q1"], assigned_by=actor)


def test_one_socket_one_berth_and_the_refusal_names_the_other_berth(db, marina_id):
    cab = _krk(db, marina_id)
    b1, b2 = _berth(db, marina_id, cab, 1), _berth(db, marina_id, cab, 2)
    svc.set_berth_outlets(db, b1, ["Q1"], assigned_by="admin@lika")
    with pytest.raises(svc.DomainError, match="A-01"):
        svc.set_berth_outlets(db, b2, ["Q1"], assigned_by="admin@lika")


def test_a_berth_has_at_most_one_socket(db, marina_id):
    cab = _krk(db, marina_id)
    b = _berth(db, marina_id, cab, 1)
    with pytest.raises(svc.DomainError, match="at most one"):
        svc.set_berth_outlets(db, b, ["Q1", "Q2"], assigned_by="admin@lika")


def test_a_valve_may_be_shared(db, marina_id):
    cab = _krk(db, marina_id)
    b3, b4 = _berth(db, marina_id, cab, 3), _berth(db, marina_id, cab, 4)
    svc.set_berth_outlets(db, b3, ["Q3", "V1"], assigned_by="admin@lika")
    svc.set_berth_outlets(db, b4, ["Q4", "V1"], assigned_by="admin@lika")


def test_retrofit_mapping_cannot_name_a_valve(db, marina_id):
    cab = _krk(db, marina_id, "retrofit")
    b = _berth(db, marina_id, cab, 1)
    with pytest.raises(svc.DomainError, match="no outlet V1"):
        svc.set_berth_outlets(db, b, ["V1"], assigned_by="admin@lika")


def test_comparison_is_unverifiable_while_the_cabinet_side_is_missing(db, marina_id):
    cab = _krk(db, marina_id)
    b = _berth(db, marina_id, cab, 1)
    svc.set_berth_outlets(db, b, ["Q1"], assigned_by="admin@lika")
    assert svc.compare_mapping(db, cab.id).state == "unverifiable"   # never "in_sync"


def test_comparison_finds_divergence_and_agreement(db, marina_id):
    from app.models.berth import BerthOutletCabinet
    cab = _krk(db, marina_id)
    b = _berth(db, marina_id, cab, 1)
    svc.set_berth_outlets(db, b, ["Q1"], assigned_by="admin@lika")
    db.add(BerthOutletCabinet(cabinet_id=cab.id, outlet_name="Q1", cabinet_berth_id=2))
    db.commit()
    r = svc.compare_mapping(db, cab.id)
    assert r.state == "divergent"
    assert r.divergent == [{"outlet_name": "Q1", "erp_berths": [1], "cabinet_berths": [2]}]
    row = db.query(BerthOutletCabinet).first()
    row.cabinet_berth_id = 1
    db.commit()
    assert svc.compare_mapping(db, cab.id).state == "in_sync"


# ─── NFC import, Krk (D6.1) ──────────────────────────────────────────────────

def test_krk_csv_import_hits_the_exact_outlet(db, marina_id):
    """End-of-phase criterion: every Krk tag, in BOTH byte orders, resolves to
    the outlet D6.1 names — not merely to "a known tag"."""
    cab = _krk(db, marina_id)
    rows = _d61_table()
    report = nfc_tags.import_csv(db, cab, _csv(rows), provisioned_by="installer@lika")
    assert report.ok and len(report.added) == 6, report.errors
    for outlet, uid, rev in rows:
        for form, expected_form in ((uid, "primary"), (rev, "reversed")):
            hit = nfc_tags.lookup(db, form)
            assert hit is not None, f"{outlet}: {form} not found"
            assert (hit.display_id, hit.outlet_name) == ("MAR_KRK_ORM_01", outlet), form
            assert hit.matched_form == expected_form


def test_reimport_is_idempotent(db, marina_id):
    cab = _krk(db, marina_id)
    nfc_tags.import_csv(db, cab, _csv(_d61_table()), provisioned_by="installer@lika")
    again = nfc_tags.import_csv(db, cab, _csv(_d61_table()), provisioned_by="installer@lika")
    assert again.ok and not again.added and len(again.unchanged) == 6


def test_moving_a_tag_by_import_is_refused_and_nothing_is_written(db, marina_id):
    from app.models.berth import OutletNfcTag
    cab = _krk(db, marina_id)
    rows = _d61_table()
    nfc_tags.import_csv(db, cab, _csv(rows[:1]), provisioned_by="installer@lika")   # Q1
    moved = [("Q2", rows[0][1], rows[0][2])] + rows[2:]                            # Q1's tag on Q2
    r = nfc_tags.import_csv(db, cab, _csv(moved), provisioned_by="installer@lika")
    assert not r.ok and "never done by import" in " ".join(r.errors)
    assert db.query(OutletNfcTag).count() == 1, "all-or-nothing: the good lines were written"


def test_a_mistyped_reversed_form_is_refused(db, marina_id):
    cab = _krk(db, marina_id)
    o, uid, rev = _d61_table()[0]
    typo = rev[:-1] + ("6" if rev[-1] != "6" else "7")
    r = nfc_tags.import_csv(db, cab, _csv([(o, uid, typo)]), provisioned_by="installer@lika")
    assert not r.ok and "byte-reverse" in r.errors[0]


def test_import_into_a_retrofit_refuses_water_tags(db, marina_id):
    cab = _krk(db, marina_id, "retrofit")
    r = nfc_tags.import_csv(db, cab, _csv(_d61_table()), provisioned_by="installer@lika")
    assert not r.ok and any("no outlet 'V1'" in e for e in r.errors)


def test_import_without_provisioned_by_is_refused(db, marina_id):
    cab = _krk(db, marina_id)
    with pytest.raises(svc.DomainError):
        nfc_tags.import_csv(db, cab, _csv(_d61_table()), provisioned_by=" ")


# ─── credit ledger (D9, §4.5) ────────────────────────────────────────────────

def test_credit_ledger_rows_are_each_checkable(db, marina_id):
    from app.models.billing import CreditLedger, Customer
    c = Customer(marina_id=marina_id, full_name="K")
    db.add(c)
    db.commit()
    credit.post(db, customer_id=c.id, delta="20.00", reason="topup", created_by="recepcija")
    credit.post(db, customer_id=c.id, delta="-3.25", reason="adjustment", created_by="recepcija")
    assert credit.balance(db, c.id) == Decimal("16.75")
    prev = Decimal("0")
    for row in db.query(CreditLedger).filter(CreditLedger.customer_id == c.id).order_by(CreditLedger.id):
        assert prev + Decimal(str(row.delta)) == Decimal(str(row.balance_after))
        prev = Decimal(str(row.balance_after))


@pytest.mark.parametrize("kw,msg", [
    (dict(delta="5", reason="topup", created_by=""), "created_by"),
    (dict(delta="-5", reason="topup", created_by="r"), "positive"),
    (dict(delta="0", reason="adjustment", created_by="r"), "zero"),
    (dict(delta="5", reason="gift", created_by="r"), "reason"),
])
def test_credit_post_refusals(db, marina_id, kw, msg):
    from app.models.billing import Customer
    c = Customer(marina_id=marina_id, full_name="K")
    db.add(c)
    db.commit()
    with pytest.raises(svc.DomainError, match=msg):
        credit.post(db, customer_id=c.id, **kw)


# ─── the admin API ───────────────────────────────────────────────────────────

def test_api_end_to_end_cabinet_berth_mapping_tags(client, admin_headers, marina_id, db):
    r = client.post(f"/api/marinas/{marina_id}/cabinets", headers=admin_headers,
                    json={"pedestal_pk": 1, "display_id": "MAR_KRK_ORM_01", "device_type": "full"})
    assert r.status_code == 201, r.text
    cab = r.json()
    assert cab["mapping_comparison"]["state"] == "unverifiable"
    assert {o["name"] for o in cab["outlets"]} == {"Q1", "Q2", "Q3", "Q4", "V1", "V2"}

    r = client.post(f"/api/marinas/{marina_id}/berth-registry", headers=admin_headers,
                    json={"berth_number": "A-01", "cabinet_id": cab["id"], "cabinet_berth_id": 1})
    assert r.status_code == 201, r.text
    berth = r.json()
    r = client.put(f"/api/marinas/{marina_id}/berth-registry/{berth['id']}/outlets",
                   headers=admin_headers, json={"outlets": ["Q1", "V1"]})
    assert r.status_code == 200, r.text
    assert {o["assigned_by"] for o in r.json()["outlets"]} == {"superadmin@test.erp"}
    assert r.json()["mapping_comparison"] == "unverifiable"

    r = client.post(f"/api/marinas/{marina_id}/cabinets/{cab['id']}/nfc-tags/import",
                    headers={**admin_headers, "Content-Type": "text/csv"},
                    content=_csv(_d61_table()))
    assert r.status_code == 200 and r.json()["added"] == 6, r.text
    r = client.get(f"/api/marinas/{marina_id}/nfc-tags/lookup", headers=admin_headers,
                   params={"uid": "E0:04:01:09:04:5A:A8:64"})
    assert r.json() == {"cabinet": "MAR_KRK_ORM_01", "outlet": "V1", "matched_form": "reversed"}


def test_api_rule_violation_is_a_409_with_the_reason(client, admin_headers, marina_id, db):
    cab = _krk(db, marina_id)
    b1, b2 = _berth(db, marina_id, cab, 1), _berth(db, marina_id, cab, 2)
    client.put(f"/api/marinas/{marina_id}/berth-registry/{b1.id}/outlets",
               headers=admin_headers, json={"outlets": ["Q1"]})
    r = client.put(f"/api/marinas/{marina_id}/berth-registry/{b2.id}/outlets",
                   headers=admin_headers, json={"outlets": ["Q1"]})
    assert r.status_code == 409 and "A-01" in r.json()["detail"]["sentence"]


def test_api_a_marina_manager_cannot_change_the_mapping(client, manager_headers, marina_id, db):
    cab = _krk(db, marina_id)
    b = _berth(db, marina_id, cab, 1)
    r = client.put(f"/api/marinas/{marina_id}/berth-registry/{b.id}/outlets",
                   headers=manager_headers, json={"outlets": ["Q1"]})
    assert r.status_code == 403
    # D20: the mapping is configuration — a Marina Manager does not even see it
    r = client.get(f"/api/marinas/{marina_id}/berth-registry", headers=manager_headers)
    assert r.status_code == 403
    r = client.get(f"/api/marinas/{marina_id}/cabinets", headers=manager_headers)
    assert r.status_code == 403
    r = client.get(f"/api/marinas/{marina_id}/nfc-tags/lookup", params={"uid": "04A1"},
                   headers=manager_headers)
    assert r.status_code == 403
    m = client.get(f"/api/marinas/{marina_id}", headers=manager_headers).json()
    assert m["pedestal_api_base_url"] is None and m["pedestal_service_email"] is None


def test_api_bad_csv_is_422_with_line_numbers(client, admin_headers, marina_id, db):
    cab = _krk(db, marina_id)
    r = client.post(f"/api/marinas/{marina_id}/cabinets/{cab.id}/nfc-tags/import",
                    headers={**admin_headers, "Content-Type": "text/csv"},
                    content="outlet,uid\nQ9,35:B2:5A:04:09:01:04:E0\n")
    assert r.status_code == 422
    assert r.json()["detail"]["errors"][0].startswith("line 2:")


def test_d61_table_uids_are_byte_reverses_of_each_other():
    """D6.1 itself is consistent — otherwise the import would refuse it."""
    for _o, uid, rev in _d61_table():
        assert both_forms(uid)[1] == rev
