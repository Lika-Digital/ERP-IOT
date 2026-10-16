"""A berth's detail and configuration (D27 phase 1, D30; spec §6.10, §6.12, §10.12).

  GET    /api/marinas/{id}/berths/{berth_id}/detail        any operator with the marina
  GET    /api/marinas/{id}/berths/{berth_id}/vessel/owner  the same, and AUDITED (D15)
  PUT    /api/marinas/{id}/berths/{berth_id}/vessel        Admin, with a reason
  DELETE /api/marinas/{id}/berths/{berth_id}/vessel        Admin, with a reason
  PUT    /api/marinas/{id}/cabinets/{cabinet_id}/reference-upload   Admin: the P1 record
  POST   /api/marinas/{id}/berths/{berth_id}/reference-photo        Admin: the photo (P5)

The detail never carries the owner: it says only whether one is recorded. Reading the
owner is its own request and every one is written to the audit log. The cabinet's
analysis comes from what the collector stored (berths.list), never from a camera
(D30). The four assessment functions the cabinet does not offer over ext yet
(R27-R30) are listed with one sentence, not drawn as controls (D3).

The reference photo (P1, P2, P5; spec §6.12) goes to the cabinet only when every check
here passes, in this order, before any call: a cabinet on the berth, a current vessel,
reason and the no-people confirmation, never a real cabinet from the demo marina, the
P1 record for that cabinet (on a real cabinet impossible until R26), Online with Smart
Mode ON, and a picture that re-encodes to a clean JPEG of at most 10 MB. It is written
to command_audit before the call and to vessel_photos after — never the picture itself.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..cabinet import marina_state
from ..database import get_db
from ..models.berth import Berth, BerthVessel, Vessel, VesselPhoto
from ..models.cabinet import Cabinet
from ..models.cache import PedestalCache
from ..models.user import User
from ..services import command_audit
from ..services import reference_photo as photo
from ..services.audit_log import record_action
from ..services.pedestal_api_factory import PedestalAPIClientFactory, get_pedestal_factory
from ..utils.time import utcnow
from ._cabinet import (cabinet_entry, cabinet_of, command, is_demo_marina,
                       refuse_real_cabinet_in_demo)
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


class UploadRecordBody(BaseModel):
    enabled: bool
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
    why_not = _upload_blocked(db, b, cab, cur, user)
    functions.insert(0, {"key": "reference_upload", "title": "Reference photo for the match",
                         "available": why_not is None, "requires": "P1, P5",
                         "sentence": why_not})
    photos = [] if cur is None else [{
        "sha256": p.sha256, "size_bytes": p.size_bytes, "uploaded_by": p.uploaded_by,
        "uploaded_at": p.uploaded_at.isoformat() + "Z", "outcome": p.outcome}
        for p in db.query(VesselPhoto).filter(VesselPhoto.berth_id == b.id,
                                              VesselPhoto.vessel_id == cur[1].id)
        .order_by(VesselPhoto.id.desc()).limit(5)]
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
        "reference": None if cab is None else {
            "cabinet_id": cab.id, "record": photo.record_view(photo.record(db, cab)),
            "photos": photos},
        "can_edit": user.role == "admin",
    }


def _upload_blocked(db: Session, b: Berth, cab: Optional[Cabinet], cur, user: User) -> Optional[str]:
    """None when the photo may go to the cabinet now; otherwise the one sentence why not.
    The upload route makes the same checks again, on the server, before any call."""
    if cab is None:
        return "No cabinet is connected to this berth yet."
    if not cab.is_simulated:
        return photo.R26_SENTENCE
    rec = photo.record(db, cab)
    if rec is None or not rec.available:
        base = (f"Not recorded for {cab.display_id}: an Admin records that its gateway "
                "allows the upload.")
        return f"{base} Switched off: {rec.note}" if rec is not None and rec.note else base
    entry = cabinet_entry(cab, demo=is_demo_marina(db, cab.marina_id))
    if not entry["controllable"]:
        return entry["sentence"]
    if cur is None:
        return "Record the vessel first: the photo belongs to it."
    if user.role != "admin":
        return "Only an Admin uploads the reference photo."
    return None


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


def _refuse(status: int, code: str, sentence: str):
    raise HTTPException(status_code=status, detail={
        "code": code, "sentence": sentence, "endpoint": "berths.push_image_ext",
        "is_stale": False, "data_as_of": None})


@router.put("/{marina_id}/cabinets/{cabinet_id}/reference-upload")
def set_upload_record(marina_id: int, cabinet_id: int, body: UploadRecordBody,
                      user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """P1: the Admin records that the cabinet's gateway allows the upload — or takes it
    back. A real cabinet cannot get the record until it ships R26 (409)."""
    require_marina_access(marina_id, user, db)
    cab = cabinet_of(db, marina_id, cabinet_id)
    try:
        row = photo.set_record(db, cab, enabled=body.enabled, by=user.email, reason=body.reason)
    except photo.PhotoRefused as exc:
        record_action(db, user_id=user.id, marina_id=marina_id, action="set_reference_upload",
                      target_id=cab.id, details={"cabinet": cab.display_id,
                                                 "enabled": body.enabled, "outcome": exc.code})
        _refuse(exc.status, exc.code, exc.sentence)
    record_action(db, user_id=user.id, marina_id=marina_id, action="set_reference_upload",
                  target_id=cab.id, details={"cabinet": cab.display_id, "enabled": body.enabled,
                                             "reason": body.reason})
    return {"ok": True, "record": photo.record_view(row)}


@router.post("/{marina_id}/berths/{berth_id}/reference-photo")
async def upload_reference_photo(
    marina_id: int, berth_id: int, request: Request,
    file: UploadFile = File(...),
    reason: str = Form(..., min_length=3, max_length=500),
    no_people_confirmed: bool = Form(...),
    user: User = Depends(require_admin), db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """P5: the reference photo to the berth's cabinet (spec §6.12). The ERP keeps no copy."""
    b = _berth(db, marina_id, berth_id, user)
    cab = db.get(Cabinet, b.cabinet_id) if b.cabinet_id else None
    if cab is None:
        _refuse(409, "no_cabinet", "No cabinet is connected to this berth yet.")
    cur = _current(db, b.id)
    if cur is None:
        _refuse(409, "no_vessel", "Record the vessel first: the photo belongs to it.")
    if not no_people_confirmed:
        _refuse(422, "people_not_confirmed",
                "Confirm that no person can be recognised in the photo (§6.10).")
    client = factory.for_cabinet(cab)
    path = {"pedestal_id": cab.pedestal_pk, "berth_id": b.cabinet_berth_id}
    url = client.url_for("berths.push_image_ext", **path)
    source_ip = request.client.host if request.client else None
    refuse_real_cabinet_in_demo(db, cab, endpoint_key="berths.push_image_ext", action="upload",
                                actor_ref=user.email, reason=reason, request_url=url,
                                source_ip=source_ip)
    why_not = _upload_blocked(db, b, cab, cur, user)
    if why_not is not None:
        rec = photo.record(db, cab)
        code = ("waiting_for_cabinet_r26" if not cab.is_simulated else
                "reference_upload_not_recorded" if rec is None or not rec.available else
                "not_controllable")
        _refuse(409, code, why_not)
    try:
        ready = photo.prepare(await file.read(photo.MAX_INPUT_BYTES + 1))
    except photo.PhotoRefused as exc:
        _refuse(exc.status, exc.code, exc.sentence)

    row = command_audit.begin(
        db, cabinet_id=cab.id, endpoint_key="berths.push_image_ext", action="upload",
        actor_type="operator", actor_ref=user.email, reason=reason, request_url=url,
        source_ip=source_ip)
    outcome = await client.push_reference_image(cab, b.cabinet_berth_id, ready.jpeg, db)
    command_audit.complete(db, row, outcome)
    if outcome.http_status in (403, 503):
        # the cabinet says the gateway does not allow it: the record no longer holds (P1)
        photo.switch_off(db, cab, f"the cabinet answered {outcome.http_status} "
                                  f"({outcome.code}) at {utcnow().isoformat(timespec='minutes')}Z")
    db.add(VesselPhoto(
        vessel_id=cur[1].id, berth_id=b.id, cabinet_id=cab.id, sha256=ready.sha256,
        size_bytes=len(ready.jpeg), content_type="image/jpeg", reason=reason,
        no_people_confirmed=True, uploaded_by=user.email, uploaded_at=utcnow(),
        outcome=outcome.code, cabinet_status=outcome.http_status,
        cabinet_detail=(outcome.cabinet_detail or None) and outcome.cabinet_detail[:1000]))
    db.commit()
    record_action(db, user_id=user.id, marina_id=marina_id, action="upload_reference_photo",
                  target_id=cur[1].id, details={"berth": b.berth_number, "cabinet": cab.display_id,
                                                "sha256": ready.sha256, "reason": reason,
                                                "outcome": outcome.code})
    out = command(outcome)
    return {**out, "sha256": ready.sha256, "size_bytes": len(ready.jpeg),
            "source_format": ready.source_format}
