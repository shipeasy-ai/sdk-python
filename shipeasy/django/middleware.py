"""Django-style middleware that mints the shared ``__se_anon_id`` cookie.

Add to ``MIDDLEWARE`` (cleaner than wrapping ``wsgi.py``)::

    MIDDLEWARE = [
        ...,
        "shipeasy.django.middleware.AnonIdMiddleware",
    ]

For any request without a valid ``__se_anon_id`` cookie it mints a UUIDv4,
binds it for the duration of the request (so gate/experiment evaluations with no
explicit ``user_id``/``anonymous_id`` bucket on it automatically), and
``Set-Cookie``s it on the response. The cookie name + format are a cross-SDK
contract (``18-identity-bucketing.md``); this reuses the same
:mod:`shipeasy._anon_id` helpers as the WSGI/ASGI middleware so all surfaces
mint identically.

This is the Django new-style ``__init__(get_response)`` + ``__call__(request)``
middleware contract — works for both WSGI and ASGI deployments (Django adapts
the sync ``__call__``).
"""

from __future__ import annotations

from typing import Callable

from .. import _anon_id as anon_id


class AnonIdMiddleware:
    """Django middleware (new-style ``__init__(get_response)``)."""

    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response

    def __call__(self, request):
        raw = request.COOKIES.get(anon_id.COOKIE)
        if anon_id.is_valid(raw):
            anon, minted = raw, False
        else:
            anon, minted = anon_id.mint(), True

        # Expose on the request and bind for the duration so evaluations default
        # to it as ``anonymous_id`` with no per-call wiring.
        request.shipeasy_anon_id = anon
        token = anon_id.set_current(anon)
        try:
            response = self.get_response(request)
        finally:
            anon_id.reset_current(token)

        if minted:
            response.set_cookie(
                anon_id.COOKIE,
                anon,
                max_age=anon_id.MAX_AGE,
                path="/",
                samesite="Lax",
                # Non-HttpOnly by design: the browser SDK reads it via
                # document.cookie to bucket identically to the server.
                httponly=False,
                secure=request.is_secure(),
            )
        return response
