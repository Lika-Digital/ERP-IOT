"""The reference photo for the cabinet's match (P1, P2, P5; spec §6.12).

- prepare(): the Admin's file -> a JPEG with no metadata at all (EXIF, GPS, device,
  ICC, comments), at most 10 MB, and the sha256 of exactly those bytes. Input JPEG,
  PNG or WebP. The picture is decoded and drawn again, so nothing of the original
  file's container survives. Nothing is written to disk (P2: the ERP keeps no copy).
- The P1 record: the ERP Admin's statement that the cabinet's gateway allows the
  upload. On a REAL cabinet it cannot be written until the cabinet ships R26 (your
  decision, 2026-10-16); until then the upload is tried on the simulator only.
  The cabinet's 403 or 503 switches the record off, with a note.
"""
from __future__ import annotations

import hashlib
import io
import warnings
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from ..models.cabinet import Cabinet, CabinetCapability
from ..utils.time import utcnow

MAX_BYTES = 10 * 1024 * 1024        # the cabinet's nginx client_max_body_size 10M (§6.12)
MAX_INPUT_BYTES = 25 * 1024 * 1024  # what the ERP reads at all, before decoding
MAX_PIXELS = 40_000_000             # a decompression bomb is refused, not decoded
INPUT_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
RECORD = "reference_upload"
R26_SENTENCE = ("Not available on a real cabinet until it ships fix R26 (the upload "
                "respects the gateway mode). Until then the upload is tried on the "
                "simulator only.")


class PhotoRefused(ValueError):
    def __init__(self, status: int, code: str, sentence: str):
        super().__init__(sentence)
        self.status, self.code, self.sentence = status, code, sentence


@dataclass(frozen=True)
class Prepared:
    jpeg: bytes
    sha256: str
    source_format: str


def prepare(data: bytes) -> Prepared:
    from PIL import Image, ImageOps

    if not data:
        raise PhotoRefused(422, "empty_image", "The file is empty.")
    if len(data) > MAX_INPUT_BYTES:
        raise PhotoRefused(413, "image_too_large",
                           "The file is larger than 25 MB; the cabinet takes at most 10 MB.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(io.BytesIO(data)) as probe:
                fmt = probe.format
                if fmt not in INPUT_FORMATS:
                    raise PhotoRefused(422, "image_type", "Only JPEG, PNG or WebP photos.")
                if probe.width * probe.height > MAX_PIXELS:
                    raise PhotoRefused(413, "image_too_large", "The photo has too many pixels.")
            with Image.open(io.BytesIO(data)) as img:
                img.load()
                # the camera's "this way up" is applied to the pixels, then every tag goes
                img = ImageOps.exif_transpose(img)
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGBA")
                    flat = Image.new("RGB", img.size, (255, 255, 255))
                    flat.paste(img, mask=img.split()[-1])
                    img = flat
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                clean = Image.new("RGB", img.size)
                clean.paste(img)                 # pixels only: no info, no exif, no icc
        except PhotoRefused:
            raise
        except (Image.DecompressionBombWarning, Image.DecompressionBombError):
            raise PhotoRefused(413, "image_too_large", "The photo has too many pixels.")
        except Exception:  # noqa: BLE001 — anything Pillow cannot read is not a photo
            raise PhotoRefused(422, "image_unreadable", "The file is not a readable photo.")
    out = io.BytesIO()
    clean.save(out, format="JPEG", quality=90, optimize=True)
    jpeg = out.getvalue()
    if len(jpeg) > MAX_BYTES:
        raise PhotoRefused(413, "image_too_large",
                           "After conversion to JPEG the photo is larger than 10 MB; "
                           "the cabinet takes at most 10 MB.")
    return Prepared(jpeg=jpeg, sha256=hashlib.sha256(jpeg).hexdigest(), source_format=fmt)


# ─── the P1 record ───────────────────────────────────────────────────────────

def record(db: Session, cab: Cabinet) -> Optional[CabinetCapability]:
    return db.get(CabinetCapability, (cab.id, RECORD))


def set_record(db: Session, cab: Cabinet, *, enabled: bool, by: str, reason: str) -> CabinetCapability:
    """The Admin records that the gateway allows the upload (or takes it back)."""
    if enabled and not cab.is_simulated:
        raise PhotoRefused(409, "waiting_for_cabinet_r26", R26_SENTENCE)
    row = record(db, cab)
    if row is None:
        row = CabinetCapability(cabinet_id=cab.id, capability=RECORD)
        db.add(row)
    row.available, row.checked_at, row.set_by, row.reason = enabled, utcnow(), by, reason
    row.note = None
    db.commit()
    return row


def switch_off(db: Session, cab: Cabinet, why: str) -> None:
    """The cabinet answered 403 or 503: the record no longer matches the cabinet."""
    row = record(db, cab)
    if row is not None and row.available:
        row.available, row.checked_at, row.note = False, utcnow(), why
        db.commit()


def record_view(row: Optional[CabinetCapability]) -> Optional[dict]:
    if row is None:
        return None
    return {"enabled": bool(row.available), "set_by": row.set_by, "reason": row.reason,
            "note": row.note, "at": row.checked_at.isoformat() + "Z" if row.checked_at else None}
