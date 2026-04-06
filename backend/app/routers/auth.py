"""Authentication router — login, me, refresh."""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import settings
from ..models.user import User, UserMarinaAccess
from ..schemas.auth import LoginRequest, TokenResponse, UserMeResponse

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer()


# ─── JWT helpers ─────────────────────────────────────────────────────────────

def _create_token(user: User, marina_ids: List[int]) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "marina_ids": marina_ids,
        "exp": expires,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        return None


def _get_marina_ids(db: Session, user: User) -> List[int]:
    if user.role == "super_admin":
        return []  # Empty list signals "all marinas" in the spec
    rows = db.query(UserMarinaAccess).filter(UserMarinaAccess.user_id == user.id).all()
    return [row.marina_id for row in rows]


# ─── Dependency: current user ─────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    payload = _decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Reject non-operator JWTs
    role = payload.get("role", "")
    if role not in ("super_admin", "marina_manager"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator access required",
        )

    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


def require_super_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    return user


def require_any_operator(user: User = Depends(get_current_user)) -> User:
    """Any authenticated operator (super_admin or marina_manager)."""
    return user


def require_marina_access(marina_id: int, user: User, db: Session) -> None:
    """Raise 403 if user cannot access the given marina."""
    if user.role == "super_admin":
        return
    access = (
        db.query(UserMarinaAccess)
        .filter(
            UserMarinaAccess.user_id == user.id,
            UserMarinaAccess.marina_id == marina_id,
        )
        .first()
    )
    if not access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this marina is not authorized",
        )


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not _pwd_ctx.verify(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Update last_login
    user.last_login = datetime.utcnow()
    db.commit()

    marina_ids = _get_marina_ids(db, user)
    token = _create_token(user, marina_ids)
    log.info(f"[AUTH] Login: {user.email} (role={user.role})")
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserMeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    marina_ids = _get_marina_ids(db, user)
    return UserMeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        marina_ids=marina_ids,
        is_active=user.is_active,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
):
    """Issue a new token with refreshed expiry if the current token is still valid."""
    payload = _decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    marina_ids = _get_marina_ids(db, user)
    token = _create_token(user, marina_ids)
    return TokenResponse(access_token=token)
