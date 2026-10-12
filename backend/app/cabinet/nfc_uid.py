"""NFC tag UIDs in both byte orders (spec §4.4, D6.1, TC-ERP-SIM-14).

A phone reports the UID of an ISO 15693 tag in one byte order or the other,
depending on the app. If the ERP keeps one form and the phone reports the
other, no tag ever matches — and it looks like "tag not recognised", not like
a byte-order problem. So every tag is stored in both forms and every lookup
checks both.

Phase 2 provides the normalisation and the lookup; phase 3 stores the two
columns (`outlet_nfc_tags.uid_primary` / `uid_reversed`) with an index each.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional, TypeVar

_HEX_PAIR = re.compile(r"^[0-9A-F]{2}$")


class UidError(ValueError):
    pass


def normalise(uid: str) -> str:
    """'35b25a0409 0104e0', '35:B2:5A:…' or '35-b2-…' -> '35:B2:5A:04:09:01:04:E0'."""
    if not isinstance(uid, str):
        raise UidError(f"UID is not a string: {uid!r}")
    compact = re.sub(r"[\s:\-]", "", uid).upper()
    if not compact or len(compact) % 2:
        raise UidError(f"UID has an odd number of hex digits: {uid!r}")
    pairs = [compact[i:i + 2] for i in range(0, len(compact), 2)]
    if not all(_HEX_PAIR.match(p) for p in pairs):
        raise UidError(f"UID is not hex: {uid!r}")
    return ":".join(pairs)


def reversed_form(uid: str) -> str:
    return ":".join(reversed(normalise(uid).split(":")))


def both_forms(uid: str) -> tuple[str, str]:
    """(as given, byte-reversed), both normalised."""
    n = normalise(uid)
    return n, reversed_form(n)


T = TypeVar("T")


def find_tag(scanned_uid: str, tags: Iterable[T], *, primary=lambda t: t.uid_primary,
             rev=lambda t: t.uid_reversed) -> Optional[T]:
    """Return the tag whose primary OR reversed form equals the scanned UID."""
    s = normalise(scanned_uid)
    for t in tags:
        if normalise(primary(t)) == s or normalise(rev(t)) == s:
            return t
    return None
