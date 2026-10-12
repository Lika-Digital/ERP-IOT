"""NFC tags: CSV import and lookup. The ERP is the only master (D6.1, D6.2).

Import is BY IMPORT, NEVER BY OVERWRITE (D6.1):
  - a UID already on the SAME outlet: skipped, reported;
  - a UID already on ANOTHER outlet: the whole file is refused — moving a tag
    changes who pays, so it is never a side effect of an import;
  - a reversed form that is not the byte-reverse of the primary: refused —
    that is exactly the typo D6.1 warns about ("sixteen characters on a
    sticker are enough to mistype");
  - all-or-nothing: one bad line, nothing is written.

Lookup checks BOTH stored forms (§4.4), and answers the exact outlet.

CSV columns: outlet,uid[,uid_reversed]   (header required)
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..cabinet.nfc_uid import UidError, both_forms, normalise
from ..models.berth import OutletNfcTag
from ..models.cabinet import Cabinet, Outlet
from .cabinets import DomainError


@dataclass
class ImportReport:
    added: list = field(default_factory=list)      # (outlet, uid)
    unchanged: list = field(default_factory=list)  # (outlet, uid)
    errors: list = field(default_factory=list)     # "line N: …"

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {"ok": self.ok, "added": len(self.added), "unchanged": len(self.unchanged),
                "errors": self.errors,
                "tags": [{"outlet": o, "uid": u} for o, u in self.added + self.unchanged]}


def _existing(db: Session, primary: str, reversed_: str) -> Optional[OutletNfcTag]:
    # a tag stored in either order matches either form
    return (db.query(OutletNfcTag)
            .filter(or_(OutletNfcTag.uid_primary.in_([primary, reversed_]),
                        OutletNfcTag.uid_reversed.in_([primary, reversed_])))
            .first())


def import_csv(db: Session, cabinet: Cabinet, csv_text: str, *,
               provisioned_by: Optional[str]) -> ImportReport:
    if provisioned_by is None or not provisioned_by.strip():
        raise DomainError("provisioned_by is required (D6.1)")
    report = ImportReport()
    outlets = {o.outlet_name: o for o in
               db.query(Outlet).filter(Outlet.cabinet_id == cabinet.id).all()}
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    if reader.fieldnames is None or not {"outlet", "uid"} <= {f.strip() for f in reader.fieldnames}:
        report.errors.append("header must contain at least: outlet,uid[,uid_reversed]")
        return report

    seen: dict = {}
    pending: list = []
    for n, row in enumerate(reader, start=2):
        row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
        name = row.get("outlet", "")
        if name not in outlets:
            report.errors.append(f"line {n}: cabinet {cabinet.display_id} has no outlet {name!r}")
            continue
        try:
            primary, rev = both_forms(row["uid"])
            if row.get("uid_reversed") and normalise(row["uid_reversed"]) != rev:
                report.errors.append(
                    f"line {n}: uid_reversed {row['uid_reversed']} is not the byte-reverse of "
                    f"{primary} (expected {rev}) — a typo would map the wrong outlet")
                continue
        except UidError as exc:
            report.errors.append(f"line {n}: {exc}")
            continue
        for form in (primary, rev):
            if form in seen and seen[form] != name:
                report.errors.append(f"line {n}: UID {primary} appears twice in the file, "
                                     f"on {seen[form]} and {name}")
        seen[primary] = seen[rev] = name

        existing = _existing(db, primary, rev)
        if existing is not None:
            current = db.get(Outlet, existing.outlet_id)
            if current.id == outlets[name].id:
                report.unchanged.append((name, primary))
            else:
                cab = db.get(Cabinet, current.cabinet_id)
                report.errors.append(
                    f"line {n}: UID {primary} is already on {cab.display_id}/{current.outlet_name}; "
                    f"moving a tag is never done by import (D6.1)")
            continue
        pending.append((outlets[name], primary, rev))

    if report.errors:
        db.rollback()
        report.added.clear()
        return report
    for o, primary, rev in pending:
        db.add(OutletNfcTag(outlet_id=o.id, uid_primary=primary, uid_reversed=rev,
                            provisioned_by=provisioned_by.strip()))
        report.added.append((o.outlet_name, primary))
    db.commit()
    return report


@dataclass(frozen=True)
class TagHit:
    cabinet_id: int
    display_id: str
    outlet_id: int
    outlet_name: str
    matched_form: str     # "primary" | "reversed"


def lookup(db: Session, scanned_uid: str) -> Optional[TagHit]:
    """The exact outlet for a scanned UID, whichever byte order the phone used."""
    s = normalise(scanned_uid)
    tag = (db.query(OutletNfcTag)
           .filter(OutletNfcTag.active.is_(True),
                   or_(OutletNfcTag.uid_primary == s, OutletNfcTag.uid_reversed == s))
           .first())
    if tag is None:
        return None
    o = db.get(Outlet, tag.outlet_id)
    cab = db.get(Cabinet, o.cabinet_id)
    return TagHit(cab.id, cab.display_id, o.id, o.outlet_name,
                  "primary" if tag.uid_primary == s else "reversed")
