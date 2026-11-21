"""Request-scoped signed DevTools overrides.

The middleware (or :func:`request_overrides`) verifies the ``se_ov`` cookie once
at scope entry against the configured engine's override key and stores the
verified map in a :class:`~contextvars.ContextVar`, so it works under threaded
WSGI servers and asyncio/ASGI alike. ``Client`` reads consult it with precedence
programmatic override > signed cookie > normal evaluation. Outside a scope, or
with no key served by Shipeasy, nothing changes.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, Optional

from ._override_cookie import (
    decode_dev_override_cookie,
    extract_override_cookie,
    verify_override_cookie,
)

_current: ContextVar[Optional[Dict[str, Dict[str, Any]]]] = ContextVar(
    "shipeasy_request_overrides", default=None
)


def current() -> Optional[Dict[str, Dict[str, Any]]]:
    """The verified override map for the current request scope, or None."""
    return _current.get()


def enter(cookie_header: Optional[str], overrides_header: Optional[str] = None):
    """Verify ``cookie_header`` (a ``Cookie:`` header or bare ``se_ov`` value)
    against the configured engine and bind the result. Returns the reset token.
    ``overrides_header`` is the ``X-Shipeasy-Overrides`` request header (cookie
    syntax, for APIs on a sibling subdomain that never see the cookie): per
    cookie name the ``Cookie`` header wins and the custom header fills in when
    the cookie is absent; the same verification and guards apply.
    Never raises; an unverifiable cookie binds ``None`` (no overrides)."""
    ov = None
    try:
        from . import _client

        engine = _client.get_global_engine()
        key = getattr(engine, "_override_key", None)
        key_id = getattr(engine, "_override_key_id", None)
        raw = extract_override_cookie(cookie_header) or extract_override_cookie(overrides_header)
        if raw and key and key_id:
            ov = verify_override_cookie(raw, key, key_id)
        # Unsigned dev-only cookie: looked at ONLY when the engine opted in and
        # the process is non-production (zero extra work in prod).
        if getattr(engine, "_dev_overrides", False):
            dev = decode_dev_override_cookie(cookie_header) or decode_dev_override_cookie(
                overrides_header
            )
            if dev:
                # Per name, the signed cookie wins over the dev cookie.
                ov = {k: {**dev[k], **((ov or {}).get(k) or {})} for k in dev}
    except Exception:  # noqa: BLE001 — fail closed
        ov = None
    return _current.set(ov)


def exit(token) -> None:  # noqa: A001
    _current.reset(token)


@contextmanager
def request_overrides(
    cookie_header: Optional[str], overrides_header: Optional[str] = None
) -> Iterator[None]:
    """Scope signed DevTools overrides to a block, for apps not using the
    middleware::

        with shipeasy.request_overrides(
            request.headers.get("Cookie"), request.headers.get("X-Shipeasy-Overrides")
        ):
            ...  # Client reads here honor a valid, signed se_ov cookie
    """
    token = enter(cookie_header, overrides_header)
    try:
        yield
    finally:
        exit(token)
