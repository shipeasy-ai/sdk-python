import asyncio

from shipeasy import _anon_id
from shipeasy.middleware import AnonIdMiddleware, AnonIdASGIMiddleware
from shipeasy._client import _with_anon_id


def _run_wsgi(environ, downstream):
    captured = {}

    def start_response(status, headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = headers

    app = AnonIdMiddleware(lambda env, sr: (downstream(env), sr("200 OK", []), [b"ok"])[-1])
    list(app(environ, start_response))
    return captured


def _set_cookie(headers):
    return [v for k, v in headers if k.lower() == "set-cookie"]


def test_wsgi_mints_and_sets_cookie():
    seen = {}
    cap = _run_wsgi(
        {"wsgi.url_scheme": "https"},
        lambda env: seen.update(id=env["shipeasy.anon_id"], cur=_anon_id.current()),
    )
    assert _anon_id.is_valid(seen["id"])
    assert seen["cur"] == seen["id"]
    cookies = _set_cookie(cap["headers"])
    assert len(cookies) == 1
    c = cookies[0]
    assert f"{_anon_id.COOKIE}={seen['id']}" in c
    assert "Path=/" in c and "Max-Age=31536000" in c and "SameSite=Lax" in c and "Secure" in c
    assert "HttpOnly" not in c
    # ContextVar cleared after the request.
    assert _anon_id.current() is None


def test_wsgi_reuses_existing_cookie():
    seen = {}
    cap = _run_wsgi(
        {"HTTP_COOKIE": f"{_anon_id.COOKIE}=stable-1; other=x"},
        lambda env: seen.update(id=env["shipeasy.anon_id"]),
    )
    assert seen["id"] == "stable-1"
    assert _set_cookie(cap["headers"]) == []


def test_wsgi_mints_on_tampered_cookie():
    seen = {}
    _run_wsgi(
        {"HTTP_COOKIE": f"{_anon_id.COOKIE}=bad value!"},
        lambda env: seen.update(id=env["shipeasy.anon_id"]),
    )
    assert seen["id"] != "bad value!"
    assert _anon_id.is_valid(seen["id"])


def test_with_anon_id_defaulting():
    token = _anon_id.set_current("anon-xyz")
    try:
        assert _with_anon_id({})["anonymous_id"] == "anon-xyz"
        assert "anonymous_id" not in _with_anon_id({"user_id": "u9"})
        assert _with_anon_id({"anonymous_id": "caller"})["anonymous_id"] == "caller"
    finally:
        _anon_id.reset_current(token)
    assert _anon_id.current() is None


def test_asgi_mints_and_sets_cookie():
    sent = []
    seen = {}

    async def downstream(scope, receive, send):
        seen["cur"] = _anon_id.current()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        return {"type": "http.request"}

    async def send(m):
        sent.append(m)

    app = AnonIdASGIMiddleware(downstream)
    asyncio.run(app({"type": "http", "scheme": "https", "headers": []}, receive, send))

    assert _anon_id.is_valid(seen["cur"])
    start = next(m for m in sent if m["type"] == "http.response.start")
    cookies = [v.decode() for k, v in start["headers"] if k == b"set-cookie"]
    assert len(cookies) == 1 and "SameSite=Lax" in cookies[0] and "Secure" in cookies[0]
    assert _anon_id.current() is None
