"""Security screen (spec §6.5, §13.1, D21) — Admin only.

The agent opens alarms; here an Admin decides: acknowledge or close, always with
a note. Nothing on this screen executes a step on a cabinet — a step is taken
with the existing ERP functions, under the Admin's own name (D21).

Every decision and every rule switch goes to auth_audit with the Admin as actor.
"""
import hashlib
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..agent.rules import RULES
from ..database import get_db
from ..models.cabinet import Cabinet
from ..models.security import AdminImport, SecurityAlarm, SecurityRuleSetting, ServiceWindow
from ..models.user import User
from ..schemas.security import (AdminImportIn, AdminImportOut, AlarmDecision, RuleMode,
                                RuleOut, SecurityAlarmOut, ServiceWindowIn, ServiceWindowOut)
from ..services import accounts, decoys
from ..utils.time import utcnow
from .auth import require_admin

router = APIRouter(prefix="/api/security", tags=["security"])
decoy_router = APIRouter(include_in_schema=False)

IMPORT_MAX_BYTES = 5 * 1024 * 1024


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _alarm_out(a: SecurityAlarm) -> SecurityAlarmOut:
    ev = a.evidence
    if isinstance(ev, str):           # SQLite hands JSON back as text when written raw
        ev = json.loads(ev)
    return SecurityAlarmOut(id=a.id, rule_id=a.rule_id, severity=a.severity, title=a.title,
                            why=a.why, evidence=ev, window_from=a.window_from,
                            window_to=a.window_to, created_at=a.created_at, state=a.state,
                            decided_by=a.decided_by, decided_at=a.decided_at,
                            decision_note=a.decision_note)


# ─── alarms ──────────────────────────────────────────────────────────────────

@router.get("/alarms", response_model=List[SecurityAlarmOut])
def list_alarms(state: Optional[str] = Query(default=None, pattern="^(open|acknowledged|closed)$"),
                limit: int = Query(default=200, ge=1, le=1000),
                admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    q = db.query(SecurityAlarm)
    if state:
        q = q.filter(SecurityAlarm.state == state)
    return [_alarm_out(a) for a in q.order_by(SecurityAlarm.id.desc()).limit(limit)]


@router.patch("/alarms/{alarm_id}", response_model=SecurityAlarmOut)
def decide_alarm(alarm_id: int, body: AlarmDecision, request: Request,
                 admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    a = db.get(SecurityAlarm, alarm_id)
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alarm not found")
    if a.state == "closed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Alarm is closed")
    if a.state == body.state:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Alarm is already {a.state}")
    old = a.state
    a.state, a.decided_by, a.decided_at = body.state, admin.id, utcnow()
    a.decision_note = body.note.strip()
    accounts.audit(db, "security_alarm_decided", actor=admin, ip=_ip(request),
                   detail=f"alarm {a.id} ({a.rule_id}): {old} -> {body.state}: {a.decision_note}")
    db.commit()
    return _alarm_out(a)


# ─── rules: shadow / active ──────────────────────────────────────────────────

@router.get("/rules", response_model=List[RuleOut])
def list_rules(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    settings = {s.rule_id: s for s in db.query(SecurityRuleSetting)}
    out = []
    for r in RULES:
        s = settings.get(r.rule_id)
        out.append(RuleOut(rule_id=r.rule_id, severity=r.severity, describe=r.describe,
                           mode=s.mode if s else "shadow",
                           decided_by=s.decided_by if s else None,
                           decided_at=s.decided_at if s else None))
    return out


@router.put("/rules/{rule_id}", response_model=RuleOut)
def set_rule_mode(rule_id: str, body: RuleMode, request: Request,
                  admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rule = next((r for r in RULES if r.rule_id == rule_id), None)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown rule")
    s = db.get(SecurityRuleSetting, rule_id)
    old = s.mode if s else "shadow"
    if s is None:
        s = SecurityRuleSetting(rule_id=rule_id)
        db.add(s)
    s.mode, s.decided_by, s.decided_at = body.mode, admin.id, utcnow()
    accounts.audit(db, "security_rule_mode", actor=admin, ip=_ip(request),
                   detail=f"{rule_id}: {old} -> {body.mode}")
    db.commit()
    return RuleOut(rule_id=rule_id, severity=rule.severity, describe=rule.describe,
                   mode=s.mode, decided_by=s.decided_by, decided_at=s.decided_at)


# ─── service windows (D16: without one the door signal raises nothing) ───────

def _window_out(w: ServiceWindow, display_id: str) -> ServiceWindowOut:
    return ServiceWindowOut(id=w.id, cabinet_id=w.cabinet_id, display_id=display_id,
                            from_at=w.from_at, to_at=w.to_at, announced_by=w.announced_by,
                            note=w.note, created_by=w.created_by, created_at=w.created_at)


@router.get("/service-windows", response_model=List[ServiceWindowOut])
def list_windows(include_past: bool = False, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    q = db.query(ServiceWindow, Cabinet.display_id).join(Cabinet,
                                                         Cabinet.id == ServiceWindow.cabinet_id)
    if not include_past:
        q = q.filter(ServiceWindow.to_at >= utcnow())
    return [_window_out(w, d) for w, d in q.order_by(ServiceWindow.from_at)]


@router.post("/service-windows", response_model=ServiceWindowOut,
             status_code=status.HTTP_201_CREATED)
def announce_window(body: ServiceWindowIn, request: Request,
                    admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    cab = db.get(Cabinet, body.cabinet_id)
    if cab is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cabinet not found")
    if body.to_at <= body.from_at:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="The window must end after it starts")
    w = ServiceWindow(cabinet_id=cab.id, from_at=body.from_at, to_at=body.to_at,
                      announced_by=body.announced_by.strip(), note=body.note,
                      created_by=admin.id, created_at=utcnow())
    db.add(w)
    accounts.audit(db, "service_window_announced", actor=admin, ip=_ip(request),
                   detail=f"{cab.display_id} {body.from_at.isoformat()}–{body.to_at.isoformat()} "
                          f"({w.announced_by})")
    db.commit()
    return _window_out(w, cab.display_id)


@router.delete("/service-windows/{window_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_window(window_id: int, request: Request, admin: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    """Only a window that has not started: a past window is the alibi of past door signals."""
    w = db.get(ServiceWindow, window_id)
    if w is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Window not found")
    if w.from_at <= utcnow():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="A window that has started cannot be cancelled")
    accounts.audit(db, "service_window_cancelled", actor=admin, ip=_ip(request),
                   detail=f"window {w.id} cabinet {w.cabinet_id}")
    db.delete(w)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── files an Admin imports by hand (D21: the agent never goes to the web) ───

@router.get("/imports", response_model=List[AdminImportOut])
def list_imports(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [AdminImportOut(id=i.id, kind=i.kind, filename=i.filename, sha256=i.sha256,
                           imported_by=i.imported_by, imported_at=i.imported_at)
            for i in db.query(AdminImport).order_by(AdminImport.id.desc())]


@router.post("/imports", response_model=AdminImportOut, status_code=status.HTTP_201_CREATED)
def import_file(body: AdminImportIn, request: Request, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    raw = json.dumps(body.content, sort_keys=True, ensure_ascii=False).encode()
    if len(raw) > IMPORT_MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                            detail="Import larger than 5 MB")
    i = AdminImport(kind=body.kind, filename=body.filename.strip(),
                    sha256=hashlib.sha256(raw).hexdigest(), content=body.content,
                    imported_by=admin.id, imported_at=utcnow())
    db.add(i)
    accounts.audit(db, "security_import", actor=admin, ip=_ip(request),
                   detail=f"{body.kind}: {i.filename} ({i.sha256[:12]})")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="This file was already imported")
    return AdminImportOut(id=i.id, kind=i.kind, filename=i.filename, sha256=i.sha256,
                          imported_by=i.imported_by, imported_at=i.imported_at)


# ─── layer 2: the decoy endpoints (no authentication — that is the point) ────

def _decoy(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    decoys.record(db, "endpoint", request.url.path, request)
    # byte for byte what FastAPI answers for a route that does not exist
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Not Found"})


for _path in decoys.DECOY_PATHS:
    decoy_router.add_api_route(_path, _decoy, methods=["GET", "POST"])
