"""
PedestalAPIClientFactory — singleton factory for per-marina PedestalAPIClient instances.

Responsibilities:
- Load marina credentials from DB.
- Decrypt the stored service account password.
- Create PedestalAPIClient instances and cache them by marina_id.
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
        data, is_stale = await client.list_pedestals(marina_id, db)
"""
import logging
from typing import Dict

from sqlalchemy.orm import Session

from ..models.marina import Marina
from ..utils.encryption import decrypt_password
from .pedestal_api import PedestalAPIClient

logger = logging.getLogger(__name__)


class PedestalAPIClientFactory:
    """
    Singleton factory.  One PedestalAPIClient per marina_id is cached in memory
    so that the JWT token cache inside each client is preserved across requests.
    """

    def __init__(self) -> None:
        self._clients: Dict[int, PedestalAPIClient] = {}

    def get_client(self, marina_id: int, db: Session) -> PedestalAPIClient:
        """
        Return the cached PedestalAPIClient for this marina.
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

        client = PedestalAPIClient(
            marina_id=marina_id,
            base_url=marina.pedestal_api_base_url,
            service_email=marina.pedestal_service_email,
            service_password=plain_password,
        )
        self._clients[marina_id] = client
        logger.debug(f"[Factory] Created PedestalAPIClient for marina {marina_id}")
        return client

    def invalidate(self, marina_id: int) -> None:
        """Remove cached client for a marina (call after credential update)."""
        self._clients.pop(marina_id, None)


# ─── Module-level singleton ───────────────────────────────────────────────────
_factory = PedestalAPIClientFactory()


def get_pedestal_factory() -> PedestalAPIClientFactory:
    """FastAPI dependency — returns the singleton factory."""
    return _factory
