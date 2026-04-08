"""Marinas router — CRUD, user access management, and connection testing."""
import logging
from typing import List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.marina import Marina
from ..models.user import User, UserMarinaAccess
from ..schemas.marina import MarinaCreate, MarinaUpdate, MarinaResponse, MarinaAccessGrant
from ..utils.encryption import encrypt_password
from .auth import get_current_user, require_super_admin, require_marina_access

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marinas", tags=["marinas"])


def _get_authorized_marina(marina_id: int, user: User, db: Session) -> Marina:
    """Fetch marina by ID and verify the user has access to it."""
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)
    return marina


@router.get("", response_model=List[MarinaResponse])
def list_marinas(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all marinas the current user can access."""
    if user.role == "super_admin":
        return db.query(Marina).order_by(Marina.name).all()
    access_rows = (
        db.query(UserMarinaAccess)
        .filter(UserMarinaAccess.user_id == user.id)
        .all()
    )
    ids = [row.marina_id for row in access_rows]
    if not ids:
        return []
    return db.query(Marina).filter(Marina.id.in_(ids)).order_by(Marina.name).all()


@router.get("/{marina_id}", response_model=MarinaResponse)
def get_marina(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _get_authorized_marina(marina_id, user, db)


@router.post("", response_model=MarinaResponse, status_code=201)
def create_marina(
    body: MarinaCreate,
    user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Create a new marina — super_admin only."""
    now = datetime.utcnow()
    # Encrypt the service account password before storing
    encrypted_password = encrypt_password(body.pedestal_service_password)

    marina = Marina(
        name=body.name,
        location=body.location,
        timezone=body.timezone,
        logo_url=body.logo_url,
        pedestal_api_base_url=body.pedestal_api_base_url,
        pedestal_service_email=body.pedestal_service_email,
        pedestal_service_password_encrypted=encrypted_password,
        webhook_secret=body.webhook_secret,
        status=body.status,
        created_at=now,
        updated_at=now,
    )
    db.add(marina)
    db.commit()
    db.refresh(marina)
    log.info(f"[MARINAS] Created marina {marina.id}: {marina.name}")
    return marina


@router.patch("/{marina_id}", response_model=MarinaResponse)
def update_marina(
    marina_id: int,
    body: MarinaUpdate,
    user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Update marina details — super_admin only."""
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")

    updates = body.model_dump(exclude_unset=True)

    # Handle password separately — encrypt before storing, remove plaintext key
    if "pedestal_service_password" in updates:
        plain = updates.pop("pedestal_service_password")
        if plain:
            updates["pedestal_service_password_encrypted"] = encrypt_password(plain)
    else:
        updates.pop("pedestal_service_password", None)

    for key, value in updates.items():
        setattr(marina, key, value)
    marina.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(marina)

    # Invalidate factory client cache so new credentials are used next request
    from ..services.pedestal_api_factory import get_pedestal_factory
    get_pedestal_factory().invalidate(marina_id)

    return marina


@router.delete("/{marina_id}", status_code=204)
def delete_marina(
    marina_id: int,
    user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Delete a marina — super_admin only."""
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    db.delete(marina)
    db.commit()


@router.post("/{marina_id}/access", status_code=204)
def grant_access(
    marina_id: int,
    body: MarinaAccessGrant,
    user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Grant a marina_manager access to a marina."""
    if not db.get(Marina, marina_id):
        raise HTTPException(status_code=404, detail="Marina not found")

    target = db.get(User, body.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    existing = (
        db.query(UserMarinaAccess)
        .filter(
            UserMarinaAccess.user_id == body.user_id,
            UserMarinaAccess.marina_id == marina_id,
        )
        .first()
    )
    if not existing:
        db.add(
            UserMarinaAccess(
                user_id=body.user_id,
                marina_id=marina_id,
                granted_at=datetime.utcnow(),
                granted_by=user.id,
            )
        )
        db.commit()


@router.delete("/{marina_id}/access/{target_user_id}", status_code=204)
def revoke_access(
    marina_id: int,
    target_user_id: int,
    user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Revoke a marina_manager's access to a marina."""
    row = (
        db.query(UserMarinaAccess)
        .filter(
            UserMarinaAccess.user_id == target_user_id,
            UserMarinaAccess.marina_id == marina_id,
        )
        .first()
    )
    if row:
        db.delete(row)
        db.commit()


# ── Step 9: Test-connection endpoint ─────────────────────────────────────────

@router.post("/{marina_id}/test-connection")
async def test_connection(
    marina_id: int,
    user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """
    Test connectivity and credentials for a marina's Pedestal SW service account.

    Returns:
        {"success": true,  "detail": "Authentication successful"}
        {"success": false, "detail": "<error message>"}
    """
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")

    if not marina.pedestal_service_email or not marina.pedestal_service_password_encrypted:
        return {"success": False, "detail": "Service account credentials not configured"}

    from ..utils.encryption import decrypt_password
    from ..services.pedestal_api import PedestalAuthError
    import httpx

    try:
        plain_password = decrypt_password(marina.pedestal_service_password_encrypted)
    except ValueError as exc:
        return {"success": False, "detail": f"Credential decryption failed: {exc}"}

    login_url = f"{marina.pedestal_api_base_url.rstrip('/')}/api/auth/service-token"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                login_url,
                json={"email": marina.pedestal_service_email, "password": plain_password},
                headers={"Accept": "application/json"},
            )
            if resp.status_code == 200:
                body = resp.json()
                if body.get("access_token"):
                    log.info(f"[MARINAS] test-connection OK for marina {marina_id}")
                    return {"success": True, "detail": "Authentication successful"}
                return {"success": False, "detail": f"Unexpected response: {body}"}
            return {
                "success": False,
                "detail": f"HTTP {resp.status_code}: {resp.text[:200]}",
            }
    except httpx.ConnectError as exc:
        return {"success": False, "detail": f"Connection refused: {exc}"}
    except httpx.TimeoutException:
        return {"success": False, "detail": "Connection timed out"}
    except Exception as exc:
        return {"success": False, "detail": f"Unexpected error: {exc}"}
