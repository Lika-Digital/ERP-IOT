"""Admin of the phase-3 model: cabinets, the berth registry, the mapping, NFC tags.

Writes are super_admin only (D18: "Admin (Lika) enters it"). The actor of every
mapping change and every tag import is the signed-in user — never a value from
the request body, never a default (D1, D6.1, D18).
"""
from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.berth import Berth, BerthOutlet, MappingComparison
from ..models.cabinet import Cabinet, CabinetCapability, Outlet
from ..models.marina import Marina
from ..models.user import User
from ..services import cabinets as svc
from ..services import nfc_tags
from ..utils.encryption import decrypt_password
from .auth import get_current_user, require_marina_access, require_super_admin

router = APIRouter(prefix="/api/marinas", tags=["cabinet-admin"])

COMPARISON_SENTENCE = {
    "unverifiable": "Nije moguće provjeriti — ormar ne izlaže svoje mapiranje (R1).",
    "in_sync": "Mapiranje ERP-a i ormara se slaže.",
    "divergent": "Mapiranje ERP-a i ormara se NE slaže — treba riješiti.",
}


def _marina(db: Session, marina_id: int) -> Marina:
    m = db.get(Marina, marina_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Marina not found")
    return m


def _cabinet(db: Session, marina_id: int, cabinet_id: int) -> Cabinet:
    c = db.get(Cabinet, cabinet_id)
    if c is None or c.marina_id != marina_id:
        raise HTTPException(status_code=404, detail="Cabinet not found in this marina")
    return c


def _refuse(exc: Exception):
    db_text = str(getattr(exc, "orig", exc))
    raise HTTPException(status_code=409, detail={"code": "rule_violated", "sentence": db_text})


class CabinetIn(BaseModel):
    pedestal_pk: int
    display_id: str = Field(min_length=1, max_length=100)
    device_type: Literal["full", "retrofit"]
    # default: the marina's cabinet server and service account
    base_url: Optional[str] = None
    service_email: Optional[str] = None
    service_password: Optional[str] = None
    erp_api_key: Optional[str] = None
    dock: Optional[str] = None


def _cabinet_out(db: Session, c: Cabinet) -> dict:
    cmp_row = db.get(MappingComparison, c.id)
    state = cmp_row.state if cmp_row else "unverifiable"
    return {
        "id": c.id, "pedestal_pk": c.pedestal_pk, "display_id": c.display_id,
        "device_type": c.device_type, "base_url": c.base_url, "dock": c.dock,
        "outlets": [{"id": o.id, "name": o.outlet_name, "medium": o.medium, "phases": o.phases,
                     "rated_amps": o.rated_amps, "rated_lpm": o.rated_lpm}
                    for o in db.query(Outlet).filter(Outlet.cabinet_id == c.id)
                    .order_by(Outlet.outlet_name)],
        "capabilities": {cap.capability: cap.available for cap in
                         db.query(CabinetCapability).filter(CabinetCapability.cabinet_id == c.id)},
        "mapping_comparison": {"state": state, "sentence": COMPARISON_SENTENCE[state],
                               "divergent": cmp_row.divergent_rows if cmp_row else None},
    }


@router.post("/{marina_id}/cabinets", status_code=201)
def create_cabinet(marina_id: int, body: CabinetIn, db: Session = Depends(get_db),
                   _: User = Depends(require_super_admin)):
    m = _marina(db, marina_id)
    password = body.service_password
    if password is None and m.pedestal_service_password_encrypted:
        password = decrypt_password(m.pedestal_service_password_encrypted)
    email = body.service_email or m.pedestal_service_email
    if not password or not email:
        raise HTTPException(status_code=422, detail="service account is required")
    try:
        c = svc.provision_cabinet(
            db, marina_id=marina_id, pedestal_pk=body.pedestal_pk, display_id=body.display_id,
            device_type=body.device_type, base_url=body.base_url or m.pedestal_api_base_url,
            service_email=email, service_password=password, erp_api_key=body.erp_api_key,
            dock=body.dock)
    except (svc.DomainError, IntegrityError) as exc:
        db.rollback()
        _refuse(exc)
    return _cabinet_out(db, c)


@router.get("/{marina_id}/cabinets")
def list_cabinets(marina_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    _marina(db, marina_id)
    require_marina_access(marina_id, user, db)
    return {"cabinets": [_cabinet_out(db, c) for c in
                         db.query(Cabinet).filter(Cabinet.marina_id == marina_id)
                         .order_by(Cabinet.id)]}


class BerthIn(BaseModel):
    berth_number: str = Field(min_length=1, max_length=50)
    cabinet_id: Optional[int] = None
    cabinet_berth_id: Optional[int] = None
    svg_id: Optional[str] = None


def _berth_out(db: Session, b: Berth) -> dict:
    rows = (db.query(BerthOutlet, Outlet).join(Outlet, Outlet.id == BerthOutlet.outlet_id)
            .filter(BerthOutlet.berth_id == b.id).order_by(Outlet.outlet_name).all())
    return {"id": b.id, "berth_number": b.berth_number, "svg_id": b.svg_id,
            "cabinet_id": b.cabinet_id, "cabinet_berth_id": b.cabinet_berth_id,
            "outlets": [{"name": o.outlet_name, "medium": o.medium, "source": bo.source,
                         "assigned_by": bo.assigned_by,
                         "assigned_at": bo.assigned_at.isoformat() + "Z"} for bo, o in rows]}


@router.post("/{marina_id}/berth-registry", status_code=201)
def create_berth(marina_id: int, body: BerthIn, db: Session = Depends(get_db),
                 _: User = Depends(require_super_admin)):
    _marina(db, marina_id)
    try:
        b = svc.create_berth(db, marina_id=marina_id, berth_number=body.berth_number,
                             cabinet_id=body.cabinet_id, cabinet_berth_id=body.cabinet_berth_id,
                             svg_id=body.svg_id)
    except (svc.DomainError, IntegrityError) as exc:
        db.rollback()
        _refuse(exc)
    return _berth_out(db, b)


@router.get("/{marina_id}/berth-registry")
def list_berth_registry(marina_id: int, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    _marina(db, marina_id)
    require_marina_access(marina_id, user, db)
    return {"berths": [_berth_out(db, b) for b in
                       db.query(Berth).filter(Berth.marina_id == marina_id)
                       .order_by(Berth.berth_number)]}


class OutletsIn(BaseModel):
    outlets: list[str]


@router.put("/{marina_id}/berth-registry/{berth_id}/outlets")
def set_outlets(marina_id: int, berth_id: int, body: OutletsIn, db: Session = Depends(get_db),
                user: User = Depends(require_super_admin)):
    b = db.get(Berth, berth_id)
    if b is None or b.marina_id != marina_id:
        raise HTTPException(status_code=404, detail="Berth not found in this marina")
    try:
        svc.set_berth_outlets(db, b, body.outlets, assigned_by=user.email)
    except (svc.DomainError, IntegrityError) as exc:
        db.rollback()
        _refuse(exc)
    out = _berth_out(db, b)
    cmp_row = db.get(MappingComparison, b.cabinet_id)
    out["mapping_comparison"] = cmp_row.state if cmp_row else "unverifiable"
    return out


@router.post("/{marina_id}/cabinets/{cabinet_id}/nfc-tags/import")
def import_nfc_tags(marina_id: int, cabinet_id: int,
                    csv_text: str = Body(..., media_type="text/csv"),
                    db: Session = Depends(get_db), user: User = Depends(require_super_admin)):
    """nfc_tags_<display_id>.csv — import, never overwrite; all-or-nothing (D6.1)."""
    cab = _cabinet(db, marina_id, cabinet_id)
    report = nfc_tags.import_csv(db, cab, csv_text, provisioned_by=user.email)
    if not report.ok:
        raise HTTPException(status_code=422, detail=report.to_dict())
    return report.to_dict()


@router.get("/{marina_id}/nfc-tags/lookup")
def lookup_nfc_tag(marina_id: int, uid: str = Query(..., min_length=2),
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The installation test: the EXACT outlet for a scanned UID, either byte order."""
    _marina(db, marina_id)
    require_marina_access(marina_id, user, db)
    try:
        hit = nfc_tags.lookup(db, uid)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    cab = db.get(Cabinet, hit.cabinet_id) if hit else None
    if hit is None or cab.marina_id != marina_id:
        raise HTTPException(status_code=404, detail="Tag is not registered in this marina")
    return {"cabinet": hit.display_id, "outlet": hit.outlet_name,
            "matched_form": hit.matched_form}
