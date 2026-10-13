"""Users — Admin only (D20: Marina Manager neither sees nor changes users).

A new user gets a one-time link, never a password typed by someone else. Every
change goes to auth_audit with the Admin as actor.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.marina import Marina
from ..models.user import AuthAudit, User, UserMarinaAccess
from ..schemas.auth import (AuthAuditOut, ReasonRequest, SetupLink, UserCreate, UserCreated,
                            UserOut, UserUpdate)
from ..services import accounts
from ..utils.time import utcnow
from .auth import require_admin

router = APIRouter(prefix="/api/users", tags=["users"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _out(db: Session, u: User) -> UserOut:
    return UserOut(id=u.id, email=u.email, full_name=u.full_name, role=u.role,
                   is_active=u.is_active, marina_ids=accounts.marina_ids(db, u),
                   password_set=u.password_hash is not None,
                   mfa_enrolled=u.totp_confirmed_at is not None,
                   locked_until=u.locked_until if accounts.is_locked(u) else None,
                   last_login=u.last_login, created_at=u.created_at)


def _get(db: Session, user_id: int) -> User:
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return u


def _set_marinas(db: Session, u: User, marina_ids: List[int], admin: User) -> None:
    known = {m.id for m in db.query(Marina.id).filter(Marina.id.in_(marina_ids))}
    unknown = sorted(set(marina_ids) - known)
    if unknown:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"Unknown marina ids: {unknown}")
    db.query(UserMarinaAccess).filter(UserMarinaAccess.user_id == u.id).delete()
    for mid in sorted(set(marina_ids)):
        db.add(UserMarinaAccess(user_id=u.id, marina_id=mid, granted_at=utcnow(),
                                granted_by=admin.id))


def _other_active_admins(db: Session, u: User) -> int:
    return db.query(User).filter(User.role == "admin", User.is_active.is_(True),
                                 User.id != u.id).count()


@router.get("", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return [_out(db, u) for u in db.query(User).order_by(User.email)]


@router.post("", response_model=UserCreated, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    email = body.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail already in use")
    u = User(email=email, full_name=body.full_name, role=body.role, is_active=True,
             password_hash=None, created_at=utcnow(), failed_count=0)
    db.add(u)
    db.flush()
    if body.role == "marina_manager":
        _set_marinas(db, u, body.marina_ids, admin)
    link, expires = accounts.issue_setup_link(db, u, settings.invite_link_hours * 60, admin)
    accounts.audit(db, "user_created", user=u, actor=admin, ip=_ip(request),
                   detail=f"role={body.role}")
    accounts.audit(db, "setup_link_issued", user=u, actor=admin, ip=_ip(request))
    db.commit()
    return UserCreated(user=_out(db, u), setup=SetupLink(link=link, expires_at=expires))


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    u = _get(db, user_id)
    changes = []
    if u.id == admin.id and ((body.role and body.role != u.role) or body.is_active is False):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="An admin cannot change their own role or disable themselves")
    demoting = (body.role == "marina_manager" and u.role == "admin") or \
               (body.is_active is False and u.role == "admin")
    if demoting and _other_active_admins(db, u) == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="The last active admin cannot be removed")
    if body.full_name is not None and body.full_name != u.full_name:
        u.full_name = body.full_name
        changes.append("full_name")
    if body.role is not None and body.role != u.role:
        changes.append(f"role {u.role}->{body.role}")
        u.role = body.role
    if body.is_active is not None and body.is_active != u.is_active:
        changes.append(f"active {u.is_active}->{body.is_active}")
        u.is_active = body.is_active
    if body.marina_ids is not None:
        _set_marinas(db, u, body.marina_ids, admin)
        changes.append(f"marinas={sorted(set(body.marina_ids))}")
    if u.role == "admin":
        db.query(UserMarinaAccess).filter(UserMarinaAccess.user_id == u.id).delete()
    if changes:
        accounts.audit(db, "user_updated", user=u, actor=admin, ip=_ip(request),
                       detail="; ".join(changes))
    db.commit()
    return _out(db, u)


@router.post("/{user_id}/setup-link", response_model=SetupLink)
def new_setup_link(user_id: int, request: Request, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    """For a new user who missed the link, or a forgotten password. 2FA stays as it is."""
    u = _get(db, user_id)
    link, expires = accounts.issue_setup_link(db, u, settings.invite_link_hours * 60, admin)
    accounts.audit(db, "setup_link_issued", user=u, actor=admin, ip=_ip(request))
    db.commit()
    return SetupLink(link=link, expires_at=expires)


@router.post("/{user_id}/mfa-reset", response_model=UserOut)
def reset_mfa(user_id: int, body: ReasonRequest, request: Request,
              db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Only for ANOTHER user, with a reason (spec §7.1). Their sessions end now."""
    u = _get(db, user_id)
    if u.id == admin.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="An admin cannot reset their own 2FA; another admin can")
    accounts.reset_mfa(db, u)
    accounts.audit(db, "mfa_reset", user=u, actor=admin, ip=_ip(request), detail=body.reason)
    db.commit()
    return _out(db, u)


@router.post("/{user_id}/unlock", response_model=UserOut)
def unlock(user_id: int, body: ReasonRequest, request: Request,
           db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    u = _get(db, user_id)
    u.locked_until = None
    u.failed_count = 0
    accounts.audit(db, "unlocked", user=u, actor=admin, ip=_ip(request), detail=body.reason)
    db.commit()
    return _out(db, u)


@router.get("/audit", response_model=List[AuthAuditOut])
def auth_audit(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db),
               _: User = Depends(require_admin)):
    return db.query(AuthAudit).order_by(AuthAudit.id.desc()).limit(limit).all()
