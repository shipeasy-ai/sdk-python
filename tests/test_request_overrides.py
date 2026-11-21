"""Signed DevTools override cookie (se_ov): verifier, request scope, middleware,
and Client reads. Fixture vectors are shared with every Shipeasy SDK."""
import asyncio

import pytest

import shipeasy
from shipeasy import Client, Engine, reset_global
from shipeasy import _client, _request_overrides
from shipeasy._override_cookie import extract_override_cookie, verify_override_cookie
from shipeasy.middleware import AnonIdASGIMiddleware, AnonIdMiddleware

KEY = "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA"
KEY_ID = "k1"
COOKIE = "eyJ2IjoxLCJwaWQiOiJwcm9qX2ZpeHR1cmUiLCJrZXlJZCI6ImsxIiwibm9uY2UiOiJmaXh0dXJlLW5vbmNlIiwiZXhwIjo0MTAyNDQ0ODAwLCJvdiI6eyJnYXRlcyI6eyJsb2JieV9ob2xkIjp0cnVlLCJvbGRfbmF2IjpmYWxzZX0sImNvbmZpZ3MiOnsiYmFubmVyIjp7InRleHQiOiJoaSJ9fSwiZXhwcyI6eyJjaGVja291dF9leHAiOiJ0cmVhdG1lbnQifX19.8qd-pHu1e96Th-jcu4BZOhLmZjwhKrgn-uI8IWBr5Og"
EXPIRED = "eyJ2IjoxLCJwaWQiOiJwcm9qX2ZpeHR1cmUiLCJrZXlJZCI6ImsxIiwibm9uY2UiOiJmaXh0dXJlLW5vbmNlIiwiZXhwIjoxMDAwLCJvdiI6eyJnYXRlcyI6eyJsb2JieV9ob2xkIjp0cnVlLCJvbGRfbmF2IjpmYWxzZX0sImNvbmZpZ3MiOnsiYmFubmVyIjp7InRleHQiOiJoaSJ9fSwiZXhwcyI6eyJjaGVja291dF9leHAiOiJ0cmVhdG1lbnQifX19.fZEp7eGjZSdi5EvTB-5NZLbZpVXbcWbIaEYRmPvPbd8"
TAMPERED = "eyJ2IjoxLCJwaWQiOiJwcm9qX2ZpeHR1cmUiLCJrZXlJZCI6ImsxIiwibm9uY2UiOiJmaXh0dXJlLW5vbmNlIiwiZXhwIjo0MTAyNDQ0ODAwLCJvdiI6eyJnYXRlcyI6eyJsb2JieV9ob2xkIjp0cnVlLCJvbGRfbmF2IjpmYWxzZX0sImNvbmZpZ3MiOnsiYmFubmVyIjp7InRleHQiOiJoaSJ9fSwiZXhwcyI6eyJjaGVja291dF9leHAiOiJ0cmVhdG1lbnQifX19.8qd-pHu1e96Th-jcu4BZOhLmZjwhKrgn-uI8IWBr5AA"

ON = {"enabled": True, "rolloutPct": 10000, "salt": "s", "rules": []}
OFF_GATE = {"enabled": False, "rolloutPct": 0, "salt": "s", "rules": []}


@pytest.fixture(autouse=True)
def _clean():
    reset_global()
    yield
    reset_global()


def _install(with_key=True):
    eng = Engine.from_snapshot(
        flags={
            "gates": {"lobby_hold": OFF_GATE, "old_nav": ON, "other": ON},
            "configs": {"banner": {"value": {"text": "orig"}}},
            "killswitches": {"ks": {"value": False}},
        },
        experiments={},
    )
    if with_key:
        eng._override_key = KEY
        eng._override_key_id = KEY_ID
    _client._global_engine = eng
    return eng


U = {"user_id": "u1"}


def test_fixture_verifies():
    ov = verify_override_cookie(COOKIE, KEY, KEY_ID)
    assert ov == {
        "gates": {"lobby_hold": True, "old_nav": False},
        "configs": {"banner": {"text": "hi"}},
        "exps": {"checkout_exp": "treatment"},
    }


def test_rejections():
    assert verify_override_cookie(EXPIRED, KEY, KEY_ID) is None
    assert verify_override_cookie(TAMPERED, KEY, KEY_ID) is None
    assert verify_override_cookie(COOKIE, KEY, "k2") is None
    assert verify_override_cookie("nodot", KEY, KEY_ID) is None
    assert verify_override_cookie(".abc", KEY, KEY_ID) is None
    assert verify_override_cookie("a.b.c", KEY, KEY_ID) is None
    assert verify_override_cookie(COOKIE, "AAAA", KEY_ID) is None


def test_extract():
    assert extract_override_cookie(COOKIE) == COOKIE
    assert extract_override_cookie(f"a=1; se_ov={COOKIE}; b=2") == COOKIE
    assert extract_override_cookie("a=1; b=2") is None
    assert extract_override_cookie(None) is None
    assert extract_override_cookie("se_ov=a%2Eb") == "a.b"


def test_scope_sets_and_clears():
    _install()
    assert _request_overrides.current() is None
    with shipeasy.request_overrides(f"x=1; se_ov={COOKIE}"):
        assert _request_overrides.current()["gates"]["lobby_hold"] is True
    assert _request_overrides.current() is None


def test_client_reads_inside_and_outside_scope():
    _install()
    c = Client(U)
    assert c.get_flag("lobby_hold") is False
    with shipeasy.request_overrides(COOKIE):
        d = c.get_flag_detail("lobby_hold")
        assert d.value is True and d.reason == shipeasy.OVERRIDE
        assert c.get_flag("old_nav") is False
        assert c.get_flag("other") is True  # not overridden
        assert c.get_config("banner") == {"text": "hi"}
        assert c.get_config("banner", decode=lambda v: v["text"]) == "hi"
    assert c.get_flag("lobby_hold") is False
    assert c.get_config("banner") == {"text": "orig"}


def test_killswitch_whole_switch_only():
    _install()
    c = Client(U)
    cookie_ks = _sign_gates({"ks": True})
    with shipeasy.request_overrides(cookie_ks):
        assert c.get_killswitch("ks") is True
        assert c.get_killswitch("ks", "sub") is False
    assert c.get_killswitch("ks") is False


def test_programmatic_override_wins():
    _install()
    shipeasy.override_flag("lobby_hold", False)
    shipeasy.override_config("banner", {"text": "prog"})
    c = Client(U)
    with shipeasy.request_overrides(COOKIE):
        assert c.get_flag("lobby_hold") is False
        assert c.get_config("banner") == {"text": "prog"}


def test_no_key_fails_closed():
    _install(with_key=False)
    c = Client(U)
    with shipeasy.request_overrides(COOKIE):
        assert _request_overrides.current() is None
        assert c.get_flag("lobby_hold") is False


def test_bad_cookie_no_overrides():
    _install()
    for bad in (EXPIRED, TAMPERED, None, ""):
        with shipeasy.request_overrides(bad):
            assert _request_overrides.current() is None


def test_experiment_group_forced():
    eng = _install()
    eng._exps_blob = {
        "universes": {"u": {"param_schema": [{"name": "color", "default": "grey"}]}},
        "experiments": {
            "checkout_exp": {
                "universe": "u",
                "status": "running",
                "groups": [
                    {"name": "control", "weight": 5000, "params": {}},
                    {"name": "treatment", "weight": 5000, "params": {"color": "green"}},
                ],
            }
        },
    }
    c = Client(U)
    with shipeasy.request_overrides(COOKIE):
        a = c.universe("u").assign()
        assert a.group == "treatment"
        assert a.get("color", "x") == "green"


def test_wsgi_middleware_scopes_and_clears():
    _install()
    seen = {}

    def downstream(env, sr):
        seen["d"] = Client(U).get_flag_detail("lobby_hold")
        sr("200 OK", [])
        return [b"ok"]

    app = AnonIdMiddleware(downstream)
    list(app({"HTTP_COOKIE": f"se_ov={COOKIE}"}, lambda *a, **k: None))
    assert seen["d"].value is True and seen["d"].reason == shipeasy.OVERRIDE
    assert _request_overrides.current() is None


def test_wsgi_clears_on_error():
    _install()

    def boom(env, sr):
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        AnonIdMiddleware(boom)({"HTTP_COOKIE": f"se_ov={COOKIE}"}, lambda *a, **k: None)
    assert _request_overrides.current() is None


def test_asgi_middleware_scopes_and_clears():
    _install()
    seen = {}

    async def downstream(scope, receive, send):
        seen["v"] = Client(U).get_flag("lobby_hold")

    async def run():
        app = AnonIdASGIMiddleware(downstream)
        scope = {
            "type": "http",
            "headers": [(b"cookie", b"a=1"), (b"cookie", f"se_ov={COOKIE}".encode())],
        }
        await app(scope, None, lambda m: asyncio.sleep(0))

    asyncio.run(run())
    assert seen["v"] is True
    assert _request_overrides.current() is None


def _sign_gates(gates):
    import base64, hashlib, hmac, json

    def b(x):
        return base64.urlsafe_b64encode(x).rstrip(b"=").decode()

    exp = 4102444800
    body = b(
        json.dumps(
            {"v": 1, "pid": "p", "keyId": KEY_ID, "nonce": "n", "exp": exp, "ov": {"gates": gates}}
        ).encode()
    )
    kp = base64.urlsafe_b64decode(KEY + "=")
    ks = hmac.new(kp, f"se-ov-sess:v1:n:{exp}".encode(), hashlib.sha256).digest()
    return body + "." + b(hmac.new(ks, body.encode(), hashlib.sha256).digest())
