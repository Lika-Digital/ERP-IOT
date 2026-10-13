"""Accounts: passwords, lockout, 2FA, backup codes, setup links, auth audit (D20, spec §7.1).

One place for every rule the login and the user screens share, so the router
cannot apply one rule in one route and forget it in another.
"""
from __future__ import annotations

import base64
import hashlib
import io
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from ..config import settings
from ..models.user import AuthAudit, SetupToken, User, UserBackupCode, UserMarinaAccess
from ..utils import totp
from ..utils.encryption import decrypt_password, encrypt_password
from ..utils.time import utcnow

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
# Verified against when there is no real hash (unknown e-mail, password not set
# yet), so that path costs one bcrypt check like every other refusal; otherwise
# response time reveals whether the account exists (spec §11 O15).
DUMMY_HASH = pwd_ctx.hash("erp-iot-timing-equaliser")

PASSWORD_MIN = 12
PASSWORD_MAX_BYTES = 72        # bcrypt ignores everything after 72 bytes — refuse, never truncate
BACKUP_CODE_COUNT = 10
SCOPE_FULL, SCOPE_MFA = "full", "mfa"


# ─── audit ───────────────────────────────────────────────────────────────────

def audit(db: Session, event: str, *, user: Optional[User] = None, email: Optional[str] = None,
          detail: Optional[str] = None, actor: Optional[User] = None,
          ip: Optional[str] = None) -> None:
    db.add(AuthAudit(user_id=user.id if user else None,
                     email_tried=email if email is not None else (user.email if user else None),
                     event=event, detail=detail, actor_id=actor.id if actor else None,
                     source_ip=ip, created_at=utcnow()))


# ─── passwords and lockout ───────────────────────────────────────────────────

def password_problem(password: str) -> Optional[str]:
    if len(password) < PASSWORD_MIN:
        return f"Password must be at least {PASSWORD_MIN} characters"
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        return f"Password must be at most {PASSWORD_MAX_BYTES} bytes"
    return None


def check_password(user: Optional[User], password: str) -> bool:
    """Exactly one bcrypt check whatever the case (O15)."""
    if user is None or user.password_hash is None:
        pwd_ctx.verify(password, DUMMY_HASH)
        return False
    return pwd_ctx.verify(password, user.password_hash)


def is_locked(user: User) -> bool:
    return user.locked_until is not None and user.locked_until > utcnow()


def register_failure(db: Session, user: User, ip: Optional[str]) -> None:
    """Password and 2FA failures add up (spec §7.1). At the threshold: locked."""
    user.failed_count = (user.failed_count or 0) + 1
    if user.failed_count >= settings.lockout_threshold:
        user.locked_until = utcnow() + timedelta(minutes=settings.lockout_minutes)
        user.failed_count = 0
        audit(db, "locked", user=user, ip=ip,
              detail=f"{settings.lockout_threshold} failures, {settings.lockout_minutes} min")


def register_success(user: User) -> None:
    user.failed_count = 0
    user.locked_until = None
    user.last_login = utcnow()


# ─── tokens ──────────────────────────────────────────────────────────────────

def _mfa_stamp(user: User) -> Optional[str]:
    return user.totp_confirmed_at.isoformat() if user.totp_confirmed_at else None


def marina_ids(db: Session, user: User) -> list[int]:
    if user.role == "admin":
        return []  # empty list signals "all marinas"
    rows = db.query(UserMarinaAccess).filter(UserMarinaAccess.user_id == user.id).all()
    return [row.marina_id for row in rows]


def access_token(db: Session, user: User) -> str:
    """The real token — only after the second factor.

    `mfa_at` ties it to the 2FA the user has now: an Admin who resets someone's
    2FA ends that person's sessions, even after they enrol again.
    """
    payload = {
        "sub": str(user.id), "email": user.email, "role": user.role,
        "marina_ids": marina_ids(db, user), "scope": SCOPE_FULL, "mfa_at": _mfa_stamp(user),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def mfa_token(user: User) -> str:
    """Opens only the 2FA step (verify or enrol), for a few minutes."""
    payload = {
        "sub": str(user.id), "scope": SCOPE_MFA,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.mfa_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        return None


def full_token_matches(user: User, payload: dict) -> bool:
    return (payload.get("scope") == SCOPE_FULL and user.totp_confirmed_at is not None
            and payload.get("mfa_at") == _mfa_stamp(user))


# ─── 2FA ─────────────────────────────────────────────────────────────────────

def start_enrolment(user: User) -> tuple[str, str, str]:
    """A new secret, stored encrypted; NOT confirmed until a code proves the phone has it."""
    import segno

    secret = totp.new_secret()
    user.totp_secret_enc = encrypt_password(secret)
    user.totp_confirmed_at = None
    user.totp_last_step = None
    uri = totp.provisioning_uri(secret, user.email)
    buf = io.BytesIO()
    segno.make(uri, error="m").save(buf, kind="svg", scale=5, border=2, xmldecl=False,
                                    svgns=True, dark="#111827", light="#ffffff")
    return secret, uri, buf.getvalue().decode()


def verify_totp(user: User, code: str) -> bool:
    if not user.totp_secret_enc:
        return False
    step = totp.verify(decrypt_password(user.totp_secret_enc), code, user.totp_last_step)
    if step is None:
        return False
    user.totp_last_step = step
    return True


def _normalise_backup(code: str) -> str:
    return code.strip().replace("-", "").replace(" ", "").lower()


def new_backup_codes(db: Session, user: User) -> list[str]:
    """Ten one-time codes; the old ones stop working. Shown once, stored as bcrypt."""
    db.query(UserBackupCode).filter(UserBackupCode.user_id == user.id).delete()
    codes = []
    for _ in range(BACKUP_CODE_COUNT):
        raw = base64.b32encode(secrets.token_bytes(5)).decode().lower()   # 40 bits, 8 chars
        codes.append(f"{raw[:4]}-{raw[4:]}")
        db.add(UserBackupCode(user_id=user.id, code_hash=pwd_ctx.hash(raw), created_at=utcnow()))
    return codes


def use_backup_code(db: Session, user: User, code: str) -> bool:
    raw = _normalise_backup(code)
    if len(raw) != 8:
        return False
    for row in db.query(UserBackupCode).filter(UserBackupCode.user_id == user.id,
                                               UserBackupCode.used_at.is_(None)):
        if pwd_ctx.verify(raw, row.code_hash):
            row.used_at = utcnow()
            return True
    return False


def reset_mfa(db: Session, user: User) -> None:
    user.totp_secret_enc = None
    user.totp_confirmed_at = None
    user.totp_last_step = None
    db.query(UserBackupCode).filter(UserBackupCode.user_id == user.id).delete()


# ─── one-time setup links ────────────────────────────────────────────────────

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_setup_link(db: Session, user: User, minutes: int,
                     created_by: Optional[User] = None) -> tuple[str, datetime]:
    """A new link; every earlier unused link of this user stops working."""
    now = utcnow()
    db.query(SetupToken).filter(SetupToken.user_id == user.id,
                                SetupToken.used_at.is_(None)).update({"used_at": now})
    raw = secrets.token_urlsafe(32)
    expires = now + timedelta(minutes=minutes)
    db.add(SetupToken(token_hash=_hash_token(raw), user_id=user.id, created_at=now,
                      expires_at=expires, created_by=created_by.id if created_by else None))
    # the token travels in the fragment: browsers never send it to a server or a log
    link = f"{settings.public_base_url.rstrip('/')}/setup#token={raw}"
    return link, expires


def find_setup_token(db: Session, raw: str) -> Optional[SetupToken]:
    row = db.query(SetupToken).filter(SetupToken.token_hash == _hash_token(raw)).first()
    if row is None or row.used_at is not None or row.expires_at <= utcnow():
        return None
    return row
