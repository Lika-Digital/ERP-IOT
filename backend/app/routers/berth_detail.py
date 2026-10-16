"""A berth's detail and configuration (D27 phase 1, D30; spec §6.10, §6.12, §10.12).

  GET    /api/marinas/{id}/berths/{berth_id}/detail        any operator with the marina
  GET    /api/marinas/{id}/berths/{berth_id}/vessel/owner  the same, and AUDITED (D15)
  PUT    /api/marinas/{id}/berths/{berth_id}/vessel        Admin, with a reason
  DELETE /api/marinas/{id}/berths/{berth_id}/vessel        Admin, with a reason

The detail never carries the owner: it says only whether one is recorded. Reading the
owner is its own request and every one is written to the audit log. The cabinet's
analysis comes from what the collector stored (berths.list), never from a camera
(D30). The four assessment functions the cabinet does not offer over ext yet
(R27-R30) are listed with one sentence, not drawn as controls (D3).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..cabinet import marina_state
from ..database import get_db
from ..models.berth import Berth, BerthVessel, Vessel
from ..models.cabinet import Cabinet
from ..models.cache import PedestalCache
from ..models.user import User
from ..services.audit_log import record_action
from ..utils.time import utcnow
from .auth import get_current_user, require_admin, require_marina_access

router = APIRouter(prefix="/api/marinas", tags=["berth-detail"])

NOT_ON_CABINET = "Not available on this cabinet"
# D30 phase 1: what the ERP will offer once the cabinet does (§7.2); one sentence each
FUNCTIONS = (
    ("occupancy_run", "Run occupancy analysis", "R27"),
    ("match_run", "Run vessel match", "R28"),
    ("sector", "Camera sector", "R29"),
    ("guard", "Guard on / off", "R30"),
)


class VesselBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    registration: Optional[str] = Field(default=None, max_length=60)
    owner_name: Optional[str] = Field(default=None, max_length=200)
    owner_contact: Optional[str] = Field(default=None, max_length=320)
    reason: str = Field(min_length=3, max_length=500)


class ReasonBody(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


def _berth(db: Session, marina_id: int, berth_id: int, user: User) -> Berth:
    require_marina_access(marina_id, user, db)
    b = db.get(Berth, berth_id)
    if b is None or b.marina_id != marina_id:
        raise HTTPException(status_code=404, detail="Berth not found")
    return b


def _current(db: Session, berth_id: int) -> Optional[tuple[BerthVessel, Vessel]]:
    row = (db.query(BerthVessel, Vessel).join(Vessel, Vessel.id == BerthVessel.vessel_id)
           .filter(BerthVessel.berth_id == berth_id, BerthVessel.valid_to.is_(None)).first())
    return (row[0], row[1]) if row else None


def _analysis(db: Session, b: Berth, cab: Cabinet, now) -> Optional[dict]:
    """The cabinet's own result for this berth, from the stored berths.list (D30: a result,
    never a picture). None when the collector has nothing for this cabinet yet."""
    rows = {r.cache_key: r for r in db.query(PedestalCache).filter(
        PedestalCache.marina_id == b.marina_id, PedestalCache.cache_key.isnot(None))}
    out = marina_state._stored(rows, "berths.list", cab.base_url.rstrip("/"), now, False)
    if out is None or not isinstance(out.data, list):
        return None
    row = next((r for r in out.data if isinstance(r, dict) and r.get("id") == b.cabinet_berth_id
                and r.get("pedestal_id") == cab.pedestal_pk), None)
    if row is None:
        return None
    code = row.get("state_code")
    occ = row.get("occupied_bit")
    return {
        "occupied": None if occ is None else bool(occ),
        # state_code: 0 no vessel, 1 the right one, 2 another one (berths.list, §3.1)
        "match": {1: "match", 2: "no_match"}.get(code) if row.get("last_analyzed") else None,
        "score": row.get("match_score"),
        "analysed_at": row.get("last_analyzed"),
        "reference_images": row.get("reference_image_count"),
        "is_stale": out.is_stale,
        "data_as_of": out.synced_at.isoformat() + "Z" if out.synced_at else None,
    }


@router.get("/{marina_id}/berths/{berth_id}/detail")
def berth_detail(marina_id: int, berth_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    b = _berth(db, marina_id, berth_id, user)
    now = utcnow()
    state = next((r for r in marina_state.build(db, marina_id, now)["berths"]
                  if r["berth_id"] == b.id), None)
    cab = db.get(Cabinet, b.cabinet_id) if b.cabinet_id else None
    cur = _current(db, b.id)
    functions = [{"key": k, "title": t, "available": False, "sentence": NOT_ON_CABINET,
                  "requires": r} for k, t, r in FUNCTIONS]
    # the upload exists on the cabinet, but the ERP's own checks wait for P1/P2 (§6.12)
    functions.insert(0, {"key": "reference_upload", "title": "Reference photo for the match",
                         "available": False, "requires": "P1, P2",
                         "sentence": "Not available yet — waiting for a decision (spec §6.12)"})
    return {
        "berth": state,
        "cabinet": None if cab is None else {"display_id": cab.display_id,
                                             "simulated": bool(cab.is_simulated)},
        "vessel": None if cur is None else {
            "name": cur[1].name, "registration": cur[1].registration,
            "has_owner": bool(cur[1].owner_name or cur[1].owner_contact),
            "since": cur[0].valid_from.isoformat() + "Z"},
        "analysis": _analysis(db, b, cab, now) if cab is not None else None,
        "functions": functions,
        "can_edit": user.role == "admin",
    }


@router.get("/{marina_id}/berths/{berth_id}/vessel/owner")
def vessel_owner(marina_id: int, berth_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    b = _berth(db, marina_id, berth_id, user)
    cur = _current(db, b.id)
    if cur is None:
        raise HTTPException(status_code=404, detail="No vessel on this berth")
    # D15: who read whose data, and when — never the data itself
    record_action(db, user_id=user.id, marina_id=marina_id, action="read_vessel_owner",
                  target_id=cur[1].id, details={"berth": b.berth_number})
    return {"owner_name": cur[1].owner_name, "owner_contact": cur[1].owner_contact}


@router.put("/{marina_id}/berths/{berth_id}/vessel")
def set_vessel(marina_id: int, berth_id: int, body: VesselBody,
               user: User = Depends(require_admin), db: Session = Depends(get_db)):
    b = _berth(db, marina_id, berth_id, user)
    now = utcnow()
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="The vessel needs a name")
    cur = _current(db, b.id)
    # the owner changes only when the request names it: editing a name must not wipe an
    # owner the editor never had to read (D15 — reading it is a separate, audited act)
    touch_owner = bool({"owner_name", "owner_contact"} & body.model_fields_set)
    if cur is not None:
        v = cur[1]
        owner_changed = touch_owner and (
            (v.owner_name, v.owner_contact) != (body.owner_name, body.owner_contact))
        v.name, v.registration = name, body.registration
        if touch_owner:
            v.owner_name, v.owner_contact = body.owner_name, body.owner_contact
        v.updated_at, v.updated_by = now, user.email
    else:
        owner_changed = bool(body.owner_name or body.owner_contact)
        v = Vessel(marina_id=marina_id, name=name, registration=body.registration,
                   owner_name=body.owner_name, owner_contact=body.owner_contact,
                   created_at=now, created_by=user.email)
        db.add(v)
        db.flush()
        db.add(BerthVessel(berth_id=b.id, vessel_id=v.id, valid_from=now, assigned_by=user.email))
    db.commit()
    # the reason and what changed — never the owner's data (D15)
    record_action(db, user_id=user.id, marina_id=marina_id, action="set_vessel", target_id=v.id,
                  details={"berth": b.berth_number, "reason": body.reason,
                           "owner_changed": owner_changed})
    return {"ok": True, "vessel_id": v.id}


@router.delete("/{marina_id}/berths/{berth_id}/vessel")
def clear_vessel(marina_id: int, berth_id: int, body: ReasonBody,
                 user: User = Depends(require_admin), db: Session = Depends(get_db)):
    b = _berth(db, marina_id, berth_id, user)
    cur = _current(db, b.id)
    if cur is None:
        raise HTTPException(status_code=404, detail="No vessel on this berth")
    cur[0].valid_to = utcnow()
    db.commit()
    record_action(db, user_id=user.id, marina_id=marina_id, action="clear_vessel",
                  target_id=cur[1].id, details={"berth": b.berth_number, "reason": body.reason})
    return {"ok": True}
