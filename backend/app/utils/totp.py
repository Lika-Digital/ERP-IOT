"""TOTP, RFC 6238 (HOTP, RFC 4226, over 30-second steps) — spec §4.9, D20.

Standard library only, no dependency: HMAC-SHA1, 30 s, 6 digits, window of ±1
step. Proved against the RFC 6238 Appendix B test vectors (tests/test_totp.py),
which are 8-digit — so `digits` is a parameter, and the app uses 6.

Imports nothing from the app, so the boot and browser checks can compute codes
without booting the app's settings.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1          # accept the previous and the next step too: phone clocks drift


def new_secret() -> str:
    """160 random bits (RFC 4226 §4 recommends 160), base32 without padding."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret_b32: str) -> bytes:
    s = secret_b32.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def hotp(key: bytes, counter: int, digits: int = DIGITS, digest=hashlib.sha1) -> str:
    mac = hmac.new(key, struct.pack(">Q", counter), digest).digest()
    offset = mac[-1] & 0x0F
    code = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % 10 ** digits).zfill(digits)


def step_at(unix_time: float) -> int:
    return int(unix_time // STEP_SECONDS)


def code_at(secret_b32: str, unix_time: float, digits: int = DIGITS) -> str:
    return hotp(_key(secret_b32), step_at(unix_time), digits)


def verify(secret_b32: str, code: str, last_step: int | None,
           unix_time: float | None = None) -> int | None:
    """The step the code matches, or None.

    A step at or before `last_step` never matches: the same code does not work
    twice (spec §7.1, `totp_last_step`). Every candidate is compared in constant
    time, and all of them are compared, so timing does not say which one hit.
    """
    code = (code or "").strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    now = step_at(time.time() if unix_time is None else unix_time)
    key = _key(secret_b32)
    hit = None
    for step in range(now - WINDOW, now + WINDOW + 1):
        if hmac.compare_digest(hotp(key, step), code) and hit is None:
            hit = step
    if hit is None or (last_step is not None and hit <= last_step):
        return None
    return hit


def provisioning_uri(secret_b32: str, account: str, issuer: str = "ERP-IOT") -> str:
    """otpauth:// URI that authenticator apps read from the QR code."""
    label = quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret_b32}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}")
