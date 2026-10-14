"""Layer 2 decoys on the ERP side (spec §7.1, D13): they record quietly, nobody legitimate touches them.

  endpoint   DECOY_PATHS answer exactly like a route that does not exist (404,
             {"detail": "Not Found"}) and are left out of the OpenAPI schema.
  account    a sign-in with an e-mail from DECOY_ACCOUNT_EMAILS — the user does
             not exist, so the answer is the ordinary 401, at the ordinary cost.
  api_key    a webhook carrying a key from DECOY_API_KEYS — the ordinary 401.

The BACKEND writes decoy_hits; the security agent only reads them (D21). A
decoy key is never stored: the row names which decoy it was, by position.
What the caller sent (path, User-Agent) is kept as data for the evidence.
"""
from __future__ import annotations

import hmac
import logging
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from ..config import settings
from ..models.security import DecoyHit
from ..utils.time import utcnow

log = logging.getLogger(__name__)

# The cabinet's gateway has its own decoy at /api/ext/admin/debug (§7.1); the ERP
# answers the same path, and its own admin-looking twin.
DECOY_PATHS = ("/api/ext/admin/debug", "/api/admin/debug")

_UA_MAX = 500


def _list(raw: str) -> list[str]:
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


def is_decoy_account(email: Optional[str]) -> bool:
    e = (email or "").strip().lower()
    return bool(e) and e in {x.lower() for x in _list(settings.decoy_account_emails)}


def decoy_key_name(api_key: Optional[str]) -> Optional[str]:
    """'api_key#N' when the key is decoy number N; every decoy is compared, always."""
    found = None
    for i, k in enumerate(_list(settings.decoy_api_keys), start=1):
        if hmac.compare_digest(k.encode(), (api_key or "").encode()):
            found = f"api_key#{i}"
    return found


def record(db: Session, kind: str, decoy: str, request: Optional[Request]) -> None:
    """One row in decoy_hits, in its own commit; a failure here never changes the answer."""
    try:
        db.add(DecoyHit(
            kind=kind, decoy=decoy[:200],
            method=request.method if request else None,
            path=str(request.url.path)[:2000] if request else None,
            source_ip=(request.client.host if request and request.client else None),
            user_agent=(request.headers.get("user-agent", "")[:_UA_MAX] if request else None),
            observed_at=utcnow()))
        db.commit()
    except Exception as exc:          # the decoy must stay quiet, even when it breaks
        db.rollback()
        log.warning("[DECOY] could not record a %s hit: %s", kind, exc)
