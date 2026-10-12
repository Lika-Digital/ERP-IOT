"""Cache and sync-log helpers for cabinet calls.

The client itself is app/cabinet/client.py (spec §2). What stays here is the
storage it uses: the last-known response per (marina, cache_key) for the stale
fallback, and the sync_log rows (errors, stale, and recoveries — client.py).
"""
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..models.cache import PedestalCache, SyncLog
from ..utils.time import utcnow

logger = logging.getLogger(__name__)


# ─── Cache helpers ────────────────────────────────────────────────────────────

def _update_cache(
    db: Optional[Session], marina_id: int, cache_key: str, data: Any
) -> None:
    if db is None:
        return
    try:
        entry = (
            db.query(PedestalCache)
            .filter(
                PedestalCache.marina_id == marina_id,
                PedestalCache.cache_key == cache_key,
            )
            .first()
        )
        if entry:
            entry.last_seen_data = data
            entry.last_synced_at = utcnow()
            entry.is_stale = False
        else:
            entry = PedestalCache(
                marina_id=marina_id,
                cache_key=cache_key,
                last_seen_data=data,
                last_synced_at=utcnow(),
                is_stale=False,
            )
            db.add(entry)
        db.commit()
    except Exception as exc:
        logger.warning(f"Cache update failed: {exc}")
        try:
            db.rollback()
        except Exception:
            pass


def _get_cache(
    db: Optional[Session], marina_id: int, cache_key: str
) -> Optional[Any]:
    if db is None:
        return None
    try:
        entry = (
            db.query(PedestalCache)
            .filter(
                PedestalCache.marina_id == marina_id,
                PedestalCache.cache_key == cache_key,
            )
            .first()
        )
        if entry and entry.last_seen_data is not None:
            entry.is_stale = True
            db.commit()
            return entry.last_seen_data
        return None
    except Exception:
        return None


def _write_sync_log(
    db: Optional[Session],
    marina_id: int,
    sync_type: str,
    status: str,
    started_at: datetime,
    completed_at: datetime,
    error_message: Optional[str] = None,
) -> None:
    if db is None:
        return
    try:
        entry = SyncLog(
            marina_id=marina_id,
            sync_type=sync_type,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            error_message=error_message,
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        logger.warning(f"sync_log write failed: {exc}")
        try:
            db.rollback()
        except Exception:
            pass
