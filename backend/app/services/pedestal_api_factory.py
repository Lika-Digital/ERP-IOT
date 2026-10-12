"""
PedestalAPIClientFactory — one CabinetClient (app/cabinet/client.py) per marina.

Responsibilities:
- Load marina credentials from DB.
- Decrypt the stored service account password.
- Create CabinetClient instances and cache them by marina_id.
- Provide a FastAPI dependency function.

Usage in a router:
    from ..services.pedestal_api_factory import get_pedestal_factory, PedestalAPIClientFactory

    @router.get("/{marina_id}/dashboard")
    async def get_dashboard(
        marina_id: int,
        factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
        db: Session = Depends(get_db),
    ):
        client = factory.get_client(marina_id, db)
        outcome = await client.list_pedestals(db)   # an Outcome, never an exception
"""
import logging
from typing import Dict, Optional

import httpx

from sqlalchemy.orm import Session

from ..models.marina import Marina
from ..utils.encryption import decrypt_password
from ..cabinet.client import CabinetClient

logger = logging.getLogger(__name__)


class PedestalAPIClientFactory:
    """
    Singleton factory.  One CabinetClient per marina_id is cached in memory
    so that the JWT token cache inside each client is preserved across requests.
    """

    def __init__(self) -> None:
        self._clients: Dict[int, CabinetClient] = {}
        # Tests point every client at the in-process simulator through this.
        self.transport: Optional[httpx.AsyncBaseTransport] = None
        # ...and skip real backoff waits through this (None = asyncio.sleep).
        self.sleep = None

    def get_client(self, marina_id: int, db: Session) -> CabinetClient:
        """
        Return the cached CabinetClient for this marina.
        Creates a new client on first call (or if credentials changed).

        Raises:
            ValueError: if marina not found or credentials are missing.
        """
        # Always reload from DB so credential changes take effect on next request
        # (token cache inside the client remains valid until it expires naturally)
        marina: Marina | None = db.get(Marina, marina_id)
        if marina is None:
            raise ValueError(f"Marina {marina_id} not found")

        if not marina.pedestal_service_email:
            raise ValueError(
                f"Marina {marina_id} has no pedestal_service_email configured. "
                "Set it via the marina admin form."
            )
        if not marina.pedestal_service_password_encrypted:
            raise ValueError(
                f"Marina {marina_id} has no pedestal_service_password_encrypted configured. "
                "Set it via the marina admin form."
            )
        if not marina.pedestal_api_base_url:
            raise ValueError(f"Marina {marina_id} has no pedestal_api_base_url configured.")

        # Decrypt password
        try:
            plain_password = decrypt_password(marina.pedestal_service_password_encrypted)
        except ValueError as exc:
            raise ValueError(
                f"Could not decrypt service account password for marina {marina_id}: {exc}"
            ) from exc

        # Retrieve or create the client
        existing = self._clients.get(marina_id)
        if existing is not None:
            # If credentials match, return the cached client (preserves JWT cache)
            if (
                existing.base_url == marina.pedestal_api_base_url.rstrip("/")
                and existing._service_email == marina.pedestal_service_email
            ):
                return existing
            # Credentials changed — create a fresh client
            logger.info(f"[Factory] Credentials changed for marina {marina_id} — refreshing client")

        client = CabinetClient(
            marina_id=marina_id,
            base_url=marina.pedestal_api_base_url,
            service_email=marina.pedestal_service_email,
            service_password=plain_password,
            # channel B (X-API-Key) has no caller before the NFC flow (phase 4/7);
            # its key lands with the cabinets table in phase 3 (spec §4.1)
            erp_api_key=None,
            transport=self.transport,
            **({"sleep": self.sleep} if self.sleep else {}),
        )
        self._clients[marina_id] = client
        logger.debug(f"[Factory] Created CabinetClient for marina {marina_id}")
        return client

    def invalidate(self, marina_id: int) -> None:
        """Remove cached client for a marina (call after credential update)."""
        self._clients.pop(marina_id, None)


# ─── Module-level singleton ───────────────────────────────────────────────────
_factory = PedestalAPIClientFactory()


def get_pedestal_factory() -> PedestalAPIClientFactory:
    """FastAPI dependency — returns the singleton factory."""
    return _factory
