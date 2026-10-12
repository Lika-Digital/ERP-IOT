"""
PedestalAPIClientFactory — CabinetClients (app/cabinet/client.py), built from `cabinets`.

Phase 4 (spec §11 O31): a client is built from a CABINET row — its base_url,
service account and channel-B key. Cabinets on the same cabinet server share
one client (one token), keyed by (base_url, service account).

A marina with no cabinet row yet falls back to the marina's own URL and
service account, so its screens keep working until it is provisioned; it has
no channel B and nothing is collected for it (the collector iterates cabinets).

Usage in a router:
    client = factory.get_client(marina_id, db)      # an Outcome per call, never an exception
"""
import logging
from typing import Dict, Optional

import httpx

from sqlalchemy.orm import Session

from ..models.cabinet import Cabinet
from ..models.marina import Marina
from ..utils.encryption import decrypt_password
from ..cabinet.client import CabinetClient

logger = logging.getLogger(__name__)


class PedestalAPIClientFactory:
    """One CabinetClient per (base_url, service account), so the cabinet's token is
    reused across requests and across the collector."""

    def __init__(self) -> None:
        self._clients: Dict[tuple, CabinetClient] = {}
        # Tests point every client at the in-process simulator through this.
        self.transport: Optional[httpx.AsyncBaseTransport] = None
        # ...and skip real backoff waits through this (None = asyncio.sleep).
        self.sleep = None

    def _client(self, *, marina_id: int, base_url: str, email: str, password: str,
                erp_api_key: Optional[str]) -> CabinetClient:
        key = (base_url.rstrip("/"), email)
        existing = self._clients.get(key)
        if existing is not None and existing._service_password == password \
                and existing.marina_id == marina_id:
            existing._erp_api_key = erp_api_key
            return existing
        if existing is not None:
            logger.info("[Factory] credentials changed for %s — new client", key[0])
        client = CabinetClient(
            marina_id=marina_id, base_url=base_url, service_email=email,
            service_password=password, erp_api_key=erp_api_key,
            transport=self.transport, **({"sleep": self.sleep} if self.sleep else {}),
        )
        self._clients[key] = client
        return client

    def for_cabinet(self, cab: Cabinet) -> CabinetClient:
        try:
            password = decrypt_password(cab.service_pw_enc)
            erp_key = decrypt_password(cab.erp_api_key_enc) if cab.erp_api_key_enc else None
        except ValueError as exc:
            raise ValueError(f"Could not decrypt credentials of cabinet {cab.display_id}: "
                             f"{exc}") from exc
        return self._client(marina_id=cab.marina_id, base_url=cab.base_url,
                            email=cab.service_email, password=password, erp_api_key=erp_key)

    def get_client(self, marina_id: int, db: Session) -> CabinetClient:
        """The marina's cabinet client. Raises ValueError when nothing is configured."""
        marina: Marina | None = db.get(Marina, marina_id)
        if marina is None:
            raise ValueError(f"Marina {marina_id} not found")

        cab = (db.query(Cabinet).filter(Cabinet.marina_id == marina_id)
               .order_by(Cabinet.id).first())
        if cab is not None:
            return self.for_cabinet(cab)

        # not provisioned yet: the marina's own cabinet server (pre-phase-3 model)
        if not marina.pedestal_service_email:
            raise ValueError(f"Marina {marina_id} has no pedestal_service_email configured.")
        if not marina.pedestal_service_password_encrypted:
            raise ValueError(
                f"Marina {marina_id} has no pedestal_service_password_encrypted configured.")
        if not marina.pedestal_api_base_url:
            raise ValueError(f"Marina {marina_id} has no pedestal_api_base_url configured.")
        try:
            plain_password = decrypt_password(marina.pedestal_service_password_encrypted)
        except ValueError as exc:
            raise ValueError(
                f"Could not decrypt service account password for marina {marina_id}: {exc}"
            ) from exc
        return self._client(marina_id=marina_id, base_url=marina.pedestal_api_base_url,
                            email=marina.pedestal_service_email, password=plain_password,
                            erp_api_key=None)

    def invalidate(self, marina_id: int) -> None:
        """Drop the marina's clients (call after a credential update)."""
        for k in [k for k, c in self._clients.items() if c.marina_id == marina_id]:
            self._clients.pop(k, None)


# ─── Module-level singleton ───────────────────────────────────────────────────
_factory = PedestalAPIClientFactory()


def get_pedestal_factory() -> PedestalAPIClientFactory:
    """FastAPI dependency — returns the singleton factory."""
    return _factory
