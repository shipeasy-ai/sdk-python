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
    # Experiment with no rule resolves not-in-experiment → default params.
    r = bound.get_experiment("nope", default_params={"d": True})
    assert r.in_experiment is False
    assert r.params == {"d": True}


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
