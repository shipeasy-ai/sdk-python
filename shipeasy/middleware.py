"""Drop-in WSGI / ASGI middleware that mints the shared ``__se_anon_id`` cookie.

For any request without a valid ``__se_anon_id`` cookie it mints a UUIDv4,
exposes it for the duration of the request, and ``Set-Cookie``s it on the
response. Once installed, gate/experiment evaluations with no explicit
``user_id``/``anonymous_id`` automatically bucket on the cookie id — anonymous
visitors get stable, SSR/browser-consistent bucketing with zero per-call wiring.

Both also read the browser SDK's ``X-SE-Correlation`` request header, so every
``see()`` fired while serving the request carries it as ``correlation_id`` — the
token Shipeasy joins on to link the browser's error to the server exception
behind it. Malformed tokens are dropped; it is cleared at request end.

They also verify the DevTools ``se_ov`` cookie once per request and scope the
signed overrides to it (see :func:`shipeasy.request_overrides`), so a signed-in
DevTools session's overrides reach server-side ``Client`` reads. Fail-closed.

WSGI (Flask, Django, any WSGI app)::

    from shipeasy.middleware import AnonIdMiddleware
    app.wsgi_app = AnonIdMiddleware(app.wsgi_app)

ASGI (FastAPI, Starlette)::

    from shipeasy.middleware import AnonIdASGIMiddleware
    app.add_middleware(AnonIdASGIMiddleware)
"""

from __future__ import annotations

from typing import Callable

from . import _anon_id as anon_id
from . import _request_overrides as request_ov
from ._see import clear_ambient_extras, set_correlation_id


class AnonIdMiddleware:
    """WSGI middleware."""

    def __init__(self, app: Callable) -> None:
        self.app = app

    def __call__(self, environ, start_response):
        anon, minted = anon_id.read_or_mint(environ.get("HTTP_COOKIE"))
        environ["shipeasy.anon_id"] = anon
        token = anon_id.set_current(anon)
        set_correlation_id(environ.get("HTTP_X_SE_CORRELATION"))
        ov_token = request_ov.enter(environ.get("HTTP_COOKIE"))

        def _start_response(status, headers, exc_info=None):
            if minted:
                secure = environ.get("wsgi.url_scheme") == "https" or (
                    environ.get("HTTP_X_FORWARDED_PROTO", "").split(",")[0].strip() == "https"
                )
                headers = list(headers) + [("Set-Cookie", anon_id.build_set_cookie(anon, secure))]
            return start_response(status, headers, exc_info)

        try:
            return self.app(environ, _start_response)
        finally:
            # Don't leak the id — or any ambient see() extras / correlation
            # token — onto the next request handled by this thread.
            anon_id.reset_current(token)
            request_ov.exit(ov_token)
            clear_ambient_extras()


class AnonIdASGIMiddleware:
    """Pure-ASGI middleware (HTTP scope only; other scopes pass through)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        header = b"; ".join(
            v for k, v in scope.get("headers", []) if k == b"cookie"
        ).decode("latin-1") or None
        anon, minted = anon_id.read_or_mint(header)
        token = anon_id.set_current(anon)
        set_correlation_id(_header(scope, b"x-se-correlation"))
        ov_token = request_ov.enter(header)

        async def _send(message):
            if minted and message["type"] == "http.response.start":
                secure = scope.get("scheme") == "https" or _xfp_https(scope)
                cookie = anon_id.build_set_cookie(anon, secure).encode("latin-1")
                message = dict(message)
                message["headers"] = list(message.get("headers", [])) + [(b"set-cookie", cookie)]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            anon_id.reset_current(token)
            request_ov.exit(ov_token)
            clear_ambient_extras()


def _header(scope, name: bytes):
    for k, v in scope.get("headers", []):
        if k.lower() == name:
            return v
    return None


def _xfp_https(scope) -> bool:
    for k, v in scope.get("headers", []):
        if k == b"x-forwarded-proto":
            return v.decode("latin-1").split(",")[0].strip() == "https"
    return False
