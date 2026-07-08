"""Tests for the two-part front door: shipeasy.configure() + the lightweight,
user-bound shipeasy.Client(user).

The heavy class is now ``Engine``; ``Client`` is the cheap bound handle that
reads the global engine, applies the configured ``attributes`` transform once at
construction, and forwards each call with the bound attribute map (NO user arg).
"""
import pytest

import shipeasy
from shipeasy import Client, Engine, configure, reset_global


@pytest.fixture(autouse=True)
def _clean_global():
    """Each test starts with no global engine and ends without leaking one."""
    reset_global()
    yield
    reset_global()


def _on_gate():
    # Fully-rolled, enabled gate: on for everyone with a unit id.
    return {"enabled": True, "rolloutPct": 10000, "salt": "s", "rules": []}


def _seed_engine_with(monkeypatch, gate_name="g", gate=None):
    """Patch Engine construction so configure() builds an offline engine seeded
    with a gate blob, instead of one that would hit the network."""
    snapshot = Engine.from_snapshot(
        flags={"gates": {gate_name: gate or _on_gate()}}, experiments={}
    )

    real_init = Engine.__init__

    def fake_init(self, api_key, *args, **kwargs):
        real_init(self, api_key, *args, **kwargs)
        # Make this engine behave like the offline snapshot one.
        self._test_mode = True
        self._flags_blob = dict(snapshot._flags_blob)
        self._exps_blob = dict(snapshot._exps_blob)
        self._initialized = True

    monkeypatch.setattr(Engine, "__init__", fake_init)


def test_configure_then_bound_client_get_flag(monkeypatch):
    _seed_engine_with(monkeypatch)
    configure(api_key="srv_key", init=False)
    # Identity transform: the user dict IS the attribute map.
    assert Client({"user_id": "u1"}).get_flag("g") is True
    assert Client({"user_id": "u1"}).get_flag("missing", default=True) is True


def test_attributes_transform_is_applied(monkeypatch):
    """Configure a transform from a raw user object to the attribute map and
    assert evaluation runs against the MAPPED attrs (not the raw object)."""

    class User:
        def __init__(self, uid):
            self.uid = uid

    seen = {}

    snapshot = Engine.from_snapshot(
        flags={"gates": {"g": _on_gate()}}, experiments={}
    )
    real_init = Engine.__init__

    def fake_init(self, api_key, *args, **kwargs):
        real_init(self, api_key, *args, **kwargs)
        self._test_mode = True
        self._flags_blob = dict(snapshot._flags_blob)
        self._exps_blob = dict(snapshot._exps_blob)
        self._initialized = True

    monkeypatch.setattr(Engine, "__init__", fake_init)

    real_get = Engine.get_flag

    def spy_get(self, name, user, default=False):
        seen["user"] = user
        return real_get(self, name, user, default)

    monkeypatch.setattr(Engine, "get_flag", spy_get)

    configure(api_key="srv_key", attributes=lambda u: {"user_id": u.uid}, init=False)

    assert Client(User("u42")).get_flag("g") is True
    # The engine saw the MAPPED attribute map, not the raw User object.
    assert seen["user"]["user_id"] == "u42"


def test_client_before_configure_raises():
    # reset_global() in the fixture guarantees no global engine.
    with pytest.raises(RuntimeError) as exc:
        Client({"user_id": "u1"})
    assert "configure" in str(exc.value)


def test_configure_is_first_wins(monkeypatch):
    _seed_engine_with(monkeypatch)
    first = configure(api_key="srv_key", init=False)
    second = configure(api_key="other_key", init=False)
    assert first is second
    assert shipeasy.get_global_engine() is first


def test_engine_is_default_see_client(monkeypatch):
    """configure() builds an Engine, which (last-constructed-wins) becomes the
    default backing package-level see()."""
    _seed_engine_with(monkeypatch)
    engine = configure(api_key="srv_key", init=False)
    from shipeasy import _see

    assert _see._resolve_default() is engine


def test_bound_client_forwards_config_and_experiment(monkeypatch):
    snapshot = Engine.from_snapshot(
        flags={"configs": {"c": {"value": {"x": 1}}}, "gates": {}},
        experiments={},
    )
    real_init = Engine.__init__

    def fake_init(self, api_key, *args, **kwargs):
        real_init(self, api_key, *args, **kwargs)
        self._test_mode = True
        self._flags_blob = dict(snapshot._flags_blob)
        self._exps_blob = dict(snapshot._exps_blob)
        self._initialized = True

    monkeypatch.setattr(Engine, "__init__", fake_init)
    configure(api_key="srv_key", init=False)

    bound = Client({"user_id": "u1"})
    assert bound.get_config("c") == {"x": 1}
    # Unknown universe resolves not-enrolled → get() falls back to the caller value.
    a = bound.universe("nope").assign()
    assert a.enrolled is False
    assert a.get("d", True) is True


def test_bound_client_track_reaches_engine_with_bound_id(monkeypatch):
    _seed_engine_with(monkeypatch)
    configure(api_key="srv_key", init=False)

    seen = {}

    def spy_track(self, user_id, event_name, properties=None):
        seen["user_id"] = user_id
        seen["event"] = event_name
        seen["props"] = properties

    monkeypatch.setattr(Engine, "track", spy_track)

    Client({"user_id": "u1"}).track("checkout", {"amount": 9})
    assert seen == {"user_id": "u1", "event": "checkout", "props": {"amount": 9}}


def test_bound_client_track_falls_back_to_anonymous_id(monkeypatch):
    _seed_engine_with(monkeypatch)
    configure(api_key="srv_key", init=False)

    seen = {}

    def spy_track(self, user_id, event_name, properties=None):
        seen["user_id"] = user_id

    monkeypatch.setattr(Engine, "track", spy_track)

    Client({"anonymous_id": "anon-7"}).track("signup")
    assert seen["user_id"] == "anon-7"


def test_bound_client_track_noop_without_unit(monkeypatch):
    _seed_engine_with(monkeypatch)
    configure(api_key="srv_key", init=False)

    called = {"n": 0}

    def spy_track(self, *a, **k):
        called["n"] += 1

    monkeypatch.setattr(Engine, "track", spy_track)

    # No user_id/anonymous_id and no middleware anon ⇒ no unit ⇒ no call.
    Client({"plan": "pro"}).track("checkout")
    assert called["n"] == 0


def test_bound_client_universe_assign_forwards_bound_attributes(monkeypatch):
    _seed_engine_with(monkeypatch)
    configure(api_key="srv_key", init=False)

    seen = {}

    def spy_assign(self, universe_name, user):
        seen["user"] = user
        seen["universe"] = universe_name
        from shipeasy import Assignment

        return Assignment(None, None, {})

    monkeypatch.setattr(Engine, "assign_universe", spy_assign)

    client = Client({"user_id": "u1"})
    client.universe("homepage").assign()  # no user arg — uses bound attributes
    assert seen["user"] is client.attributes
    assert seen["universe"] == "homepage"


def test_engine_and_bound_client_get_killswitch():
    engine = Engine.from_snapshot(
        flags={
            "killswitches": {
                "ks_on": {"value": True},
                "ks_off": {"value": False, "switches": {"eu": True}},
            }
        },
        experiments={},
    )
    assert engine.get_killswitch("ks_on") is True
    assert engine.get_killswitch("ks_off") is False
    assert engine.get_killswitch("ks_off", switch_key="eu") is True
    assert engine.get_killswitch("absent") is False
