"""Anonymous bucketing identity — the cross-SDK ``__se_anon_id`` cookie.

Gates and experiments bucket a unit with ``murmur3(salt:unit)``. For a logged-out
visitor the unit is a stable anonymous id carried in a single first-party cookie
that EVERY Shipeasy SDK (server + browser) reads and writes, so a server render
and the browser bucket a fractional rollout identically. The cookie name and
format are frozen across every language; see
``experiment-platform/18-identity-bucketing.md``.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar
from typing import Optional

COOKIE = "__se_anon_id"
MAX_AGE = 31_536_000  # 1 year, in seconds

# The cookie value is client-controllable and feeds bucketing, so a tampered
# value is treated as absent and a fresh id is minted. UUIDs satisfy this.
_VALID_RX = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Per-request id resolved by the middleware. A ContextVar (not thread-local)
# so it works under both threaded WSGI servers and asyncio/ASGI.
_current: ContextVar[Optional[str]] = ContextVar("shipeasy_anon_id", default=None)


def mint() -> str:
    """A fresh opaque bucketing id (UUIDv4)."""
    return str(uuid.uuid4())


def is_valid(value: Optional[str]) -> bool:
    return isinstance(value, str) and _VALID_RX.match(value) is not None


def current() -> Optional[str]:
    """The anon id the middleware resolved for the current request, or None.

    ``Engine.get_flag`` / ``assign`` fall back to this as the default
    ``anonymous_id``, so evaluations need no per-call wiring.
    """
    return _current.get()


def set_current(value: Optional[str]):
    """Bind the current-request anon id; returns the reset token."""
    return _current.set(value)


def reset_current(token) -> None:
    _current.reset(token)


def parse_cookie_header(header: Optional[str]) -> dict:
    out: dict = {}
    if not header:
        return out
    for pair in header.split(";"):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            if k and k not in out:
                out[k] = v
    return out


def read_or_mint(cookie_header: Optional[str]):
    """Return ``(id, minted)`` for a raw Cookie header value."""
    raw = parse_cookie_header(cookie_header).get(COOKIE)
    if is_valid(raw):
        return raw, False
    return mint(), True


def build_set_cookie(value: str, secure: bool) -> str:
    """Format the ``Set-Cookie`` header value per the cross-SDK contract.

    Non-HttpOnly by design — the browser SDK reads it via ``document.cookie`` to
    bucket identically to the server.
    """
    parts = [
        f"{COOKIE}={value}",
        "Path=/",
        f"Max-Age={MAX_AGE}",
        "SameSite=Lax",
    ]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)
