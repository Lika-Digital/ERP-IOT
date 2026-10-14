"""Authentication — password, then TOTP 2FA, for every user (D20, spec §7.1).

    POST /api/auth/login               email + password  -> mfa_token (opens ONLY the 2FA step)
    POST /api/auth/mfa/verify          mfa_token + code  -> access_token
    POST /api/auth/mfa/enroll/start    mfa_token         -> secret + QR (2FA not yet linked)
    POST /api/auth/mfa/enroll/confirm  mfa_token + code  -> access_token + backup codes (once)
    POST /api/auth/setup/check         one-time link     -> e-mail it belongs to
    POST /api/auth/setup               link + password   -> mfa_token
    POST /api/auth/mfa/backup-codes    access + code     -> new backup codes (once)
    GET  /api/auth/me, POST /api/auth/refresh

Every refusal says the same thing: 401 "Invalid email or password" at the
password step — unknown e-mail, wrong password, disabled, locked, no password
yet — and 401 "Invalid code" at the 2FA step. The reason goes to auth_audit.
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import ROLES, User, UserMarinaAccess
from ..schemas.auth import (BackupCodes, CodeRequest, EnrollDone, EnrollStart, LoginRequest,
                            MfaChallenge, SetupCheck, SetupCheckResponse, SetupRequest,
                            TokenResponse, UserMeResponse)
from ..services import accounts, decoys
from ..utils.time import utcnow

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

_bearer = HTTPBearer()
BAD_LOGIN = "Invalid email or password"
BAD_CODE = "Invalid code"
BAD_LINK = "This link is invalid or has expired"


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _decode_token(token: str):
    """Kept for the WebSocket endpoint: a FULL token or nothing."""
    payload = accounts.decode(token)
    if not payload or payload.get("scope") != accounts.SCOPE_FULL:
        return None
    return payload


def _get_marina_ids(db: Session, user: User) -> List[int]:
    return accounts.marina_ids(db, user)


# ─── Dependencies ────────────────────────────────────────────────────────────

def _unauthorized(detail: str = "Invalid or expired token") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail,
                         headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """A full token only: password AND second factor. An mfa token opens nothing here."""
    payload = accounts.decode(credentials.credentials)
    if not payload or payload.get("scope") != accounts.SCOPE_FULL:
        raise _unauthorized()
    if payload.get("role", "") not in ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Operator access required")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active or not accounts.full_token_matches(user, payload):
        raise _unauthorized("User not found or inactive")
    return user


def get_mfa_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    payload = accounts.decode(credentials.credentials)
    if not payload or payload.get("scope") != accounts.SCOPE_MFA:
        raise _unauthorized()
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active or user.password_hash is None:
        raise _unauthorized()
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Admin access required")
    return user


def require_any_operator(user: User = Depends(get_current_user)) -> User:
    """Any authenticated user (Admin or Marina Manager)."""
    return user


def require_marina_access(marina_id: int, user: User, db: Session) -> None:
    """Raise 403 if user cannot access the given marina."""
    if user.role == "admin":
        return
    access = (
        db.query(UserMarinaAccess)
        .filter(UserMarinaAccess.user_id == user.id, UserMarinaAccess.marina_id == marina_id)
        .first()
    )
    if not access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Access to this marina is not authorized")


# ─── Password step ───────────────────────────────────────────────────────────

@router.post("/login", response_model=MfaChallenge)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = _ip(request)
    user = db.query(User).filter(User.email == body.email).first()
    password_ok = accounts.check_password(user, body.password)   # one bcrypt check, always
    if user is None:
        reason = "unknown email"
    elif user.password_hash is None:
        reason = "no password set"
    elif accounts.is_locked(user):
        reason = "locked"
    elif not password_ok:
        reason = "wrong password"
        accounts.register_failure(db, user, ip)
    elif not user.is_active:
        reason = "account disabled"
    else:
        reason = None
    if reason:
        accounts.audit(db, "login_failed", user=user, email=body.email, detail=reason, ip=ip)
        db.commit()
        if user is None and decoys.is_decoy_account(body.email):
            decoys.record(db, "account", body.email.strip().lower(), request)   # layer 2
        log.warning("[AUTH] Login refused: %s (%s)", body.email, reason)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=BAD_LOGIN)

    accounts.audit(db, "password_ok", user=user, ip=ip)
    db.commit()
    return MfaChallenge(mfa_token=accounts.mfa_token(user),
                        mfa_enrolled=user.totp_confirmed_at is not None)


# ─── 2FA step ────────────────────────────────────────────────────────────────

def _refuse_code(db: Session, user: User, ip, detail: str):
    accounts.register_failure(db, user, ip)
    accounts.audit(db, "mfa_failed", user=user, detail=detail, ip=ip)
    db.commit()
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=BAD_CODE)


@router.post("/mfa/verify", response_model=TokenResponse)
def mfa_verify(body: CodeRequest, request: Request, user: User = Depends(get_mfa_user),
               db: Session = Depends(get_db)):
    ip = _ip(request)
    if user.totp_confirmed_at is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Two-factor authentication is not linked yet")
    if accounts.is_locked(user):
        accounts.audit(db, "mfa_failed", user=user, detail="locked", ip=ip)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=BAD_CODE)
    if accounts.verify_totp(user, body.code):
        how = "totp"
    elif accounts.use_backup_code(db, user, body.code):
        how = "backup_code"
    else:
        _refuse_code(db, user, ip, "wrong, expired or reused code")
    accounts.register_success(user)
    accounts.audit(db, "login_ok", user=user, detail=how, ip=ip)
    db.commit()
    log.info("[AUTH] Login: %s (role=%s, %s)", user.email, user.role, how)
    return TokenResponse(access_token=accounts.access_token(db, user))


@router.post("/mfa/enroll/start", response_model=EnrollStart)
def mfa_enroll_start(request: Request, user: User = Depends(get_mfa_user),
                     db: Session = Depends(get_db)):
    if user.totp_confirmed_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Two-factor authentication is already linked")
    if accounts.is_locked(user):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=BAD_CODE)
    secret, uri, svg = accounts.start_enrolment(user)
    accounts.audit(db, "mfa_enroll_started", user=user, ip=_ip(request))
    db.commit()
    return EnrollStart(secret=secret, otpauth_uri=uri, qr_svg=svg)


@router.post("/mfa/enroll/confirm", response_model=EnrollDone)
def mfa_enroll_confirm(body: CodeRequest, request: Request, user: User = Depends(get_mfa_user),
                       db: Session = Depends(get_db)):
    ip = _ip(request)
    if user.totp_confirmed_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Two-factor authentication is already linked")
    if accounts.is_locked(user) or not user.totp_secret_enc:
        accounts.audit(db, "mfa_failed", user=user, detail="enrol: locked or not started", ip=ip)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=BAD_CODE)
    if not accounts.verify_totp(user, body.code):
        _refuse_code(db, user, ip, "enrol: wrong code")
    user.totp_confirmed_at = utcnow()
    codes = accounts.new_backup_codes(db, user)
    accounts.register_success(user)
    accounts.audit(db, "mfa_enrolled", user=user, ip=ip)
    accounts.audit(db, "login_ok", user=user, detail="enrolment", ip=ip)
    db.commit()
    return EnrollDone(access_token=accounts.access_token(db, user), backup_codes=codes)


@router.post("/mfa/backup-codes", response_model=BackupCodes)
def regenerate_backup_codes(body: CodeRequest, request: Request,
                            user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """New codes need a code from the phone: a stolen session alone cannot mint them."""
    ip = _ip(request)
    if not accounts.verify_totp(user, body.code):
        _refuse_code(db, user, ip, "backup codes: wrong code")
    codes = accounts.new_backup_codes(db, user)
    accounts.audit(db, "backup_codes_regenerated", user=user, ip=ip)
    db.commit()
    return BackupCodes(backup_codes=codes)


# ─── One-time setup link (first admin, new users, D20.3) ─────────────────────

@router.post("/setup/check", response_model=SetupCheckResponse)
def setup_check(body: SetupCheck, db: Session = Depends(get_db)):
    """Does not use the link up: the page shows whose link it is before asking."""
    row = accounts.find_setup_token(db, body.token)
    if row is None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=BAD_LINK)
    return SetupCheckResponse(email=db.get(User, row.user_id).email)


@router.post("/setup", response_model=MfaChallenge)
def setup(body: SetupRequest, request: Request, db: Session = Depends(get_db)):
    ip = _ip(request)
    row = accounts.find_setup_token(db, body.token)
    if row is None:
        accounts.audit(db, "setup_failed", detail="invalid, used or expired link", ip=ip)
        db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=BAD_LINK)
    problem = accounts.password_problem(body.password)
    if problem:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=problem)
    user = db.get(User, row.user_id)
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=BAD_LINK)
    user.password_hash = accounts.pwd_ctx.hash(body.password)
    row.used_at = utcnow()
    accounts.audit(db, "setup_completed", user=user, ip=ip)
    db.commit()
    # straight on to the second factor: nothing else is open before it (D20.3)
    return MfaChallenge(mfa_token=accounts.mfa_token(user),
                        mfa_enrolled=user.totp_confirmed_at is not None)


# ─── Session ─────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserMeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return UserMeResponse(id=user.id, email=user.email, full_name=user.full_name,
                          role=user.role, marina_ids=accounts.marina_ids(db, user),
                          is_active=user.is_active)


@router.post("/refresh", response_model=TokenResponse)
def refresh(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """A new full token with a new expiry, for a user whose full token is still valid."""
    return TokenResponse(access_token=accounts.access_token(db, user))
