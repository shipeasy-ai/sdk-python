"""Environment-derived network & telemetry (egress) defaults.

The SDK is QUIET BY DEFAULT outside production: the master network switch and
usage telemetry both default ON in production and OFF everywhere else. An
explicit value always overrides. See ``shipeasy/_env.py`` and the Engine wiring.

The session-scoped ``_egress_env_is_production`` fixture in conftest.py sets
``SHIPEASY_ENV=production`` for the whole suite, so these tests explicitly
monkeypatch the env back to a dev value to exercise the OFF branch.
"""
import json

import pytest

from shipeasy import Engine, is_production_env


# ---------------------------------------------------------------------------
# is_production_env — precedence
# ---------------------------------------------------------------------------

_NATIVE_VARS = ("SHIPEASY_ENV", "APP_ENV", "ENV", "PYTHON_ENV")


def _clear_native(monkeypatch):
    for name in _NATIVE_VARS:
        monkeypatch.delenv(name, raising=False)


def test_is_production_env_native_prod_values(monkeypatch):
    _clear_native(monkeypatch)
    for val in ("production", "prod", "PRODUCTION", "Prod", "  prod  "):
        monkeypatch.setenv("SHIPEASY_ENV", val)
        assert is_production_env("dev") is True, val


def test_is_production_env_native_nonprod_values(monkeypatch):
    _clear_native(monkeypatch)
    for val in ("development", "dev", "staging", "test", "ci"):
        monkeypatch.setenv("SHIPEASY_ENV", val)
        # Even though the configured env says prod, a present native var wins.
        assert is_production_env("prod") is False, val


def test_is_production_env_var_precedence(monkeypatch):
    _clear_native(monkeypatch)
    # SHIPEASY_ENV wins over the conventional vars.
    monkeypatch.setenv("PYTHON_ENV", "production")
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SHIPEASY_ENV", "development")
    assert is_production_env() is False
    monkeypatch.setenv("SHIPEASY_ENV", "production")
    assert is_production_env() is True


def test_is_production_env_falls_through_blank_vars(monkeypatch):
    _clear_native(monkeypatch)
    # A blank SHIPEASY_ENV counts as unset; APP_ENV then decides.
    monkeypatch.setenv("SHIPEASY_ENV", "   ")
    monkeypatch.setenv("APP_ENV", "production")
    assert is_production_env("dev") is True


def test_is_production_env_conventional_vars_in_order(monkeypatch):
    _clear_native(monkeypatch)
    monkeypatch.setenv("PYTHON_ENV", "development")
    monkeypatch.setenv("ENV", "production")  # ENV precedes PYTHON_ENV
    assert is_production_env() is True


def test_is_production_env_falls_back_to_configured(monkeypatch):
    _clear_native(monkeypatch)
    assert is_production_env() is True  # configured default is prod
    assert is_production_env("prod") is True
    assert is_production_env("Prod") is True
    assert is_production_env("dev") is False
    assert is_production_env("staging") is False


# ---------------------------------------------------------------------------
# Network master switch — default branching
# ---------------------------------------------------------------------------


class _CaptureEngine(Engine):
    """Records outbound /collect posts (and marks fetches) instead of sending."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.posts = []
        self.fetches = 0

    def _post_silent(self, path, data):
        self.posts.append((path, json.loads(data.decode("utf-8"))))

    def _fetch_all(self):
        self.fetches += 1
        return False


def test_offline_by_default_in_dev(monkeypatch):
    _clear_native(monkeypatch)
    monkeypatch.setenv("SHIPEASY_ENV", "development")
    e = _CaptureEngine(api_key="k", base_url="https://e.x")
    # Fully offline: init/track/exposure/see never touch the network.
    e.init()
    e.track("u1", "purchase", {"amount": 9})
    e.universe("checkout").assign({"user_id": "u1"})
    e.see(ValueError("x")).causes_the("checkout").to("skip")
    assert e.fetches == 0
    assert e.posts == []
    # Getters still resolve (empty seeded blob + overrides).
    e.override_flag("new_checkout", True)
    assert e.get_flag("new_checkout", {"user_id": "u1"}) is True


def test_explicit_network_on_overrides_dev(monkeypatch):
    _clear_native(monkeypatch)
    monkeypatch.setenv("SHIPEASY_ENV", "development")
    e = _CaptureEngine(api_key="k", base_url="https://e.x", is_network_enabled=True)

    import shipeasy._client as cm

    class _ImmediateThread:
        def __init__(self, target, args=(), daemon=False):
            self._target, self._args = target, args

        def start(self):
            self._target(*self._args)

    orig = cm.threading.Thread
    cm.threading.Thread = _ImmediateThread  # type: ignore[assignment]
    try:
        e.init_once()
        e.track("u1", "purchase", {"amount": 9})
    finally:
        cm.threading.Thread = orig

    assert e.fetches == 1
    assert e.posts and e.posts[0][0] == "/collect"


def test_on_by_default_in_production(monkeypatch):
    _clear_native(monkeypatch)
    monkeypatch.setenv("SHIPEASY_ENV", "production")
    e = _CaptureEngine(api_key="k", base_url="https://e.x")

    import shipeasy._client as cm

    class _ImmediateThread:
        def __init__(self, target, args=(), daemon=False):
            self._target, self._args = target, args

        def start(self):
            self._target(*self._args)

    orig = cm.threading.Thread
    cm.threading.Thread = _ImmediateThread  # type: ignore[assignment]
    try:
        e.init_once()
        e.track("u1", "purchase", {"amount": 9})
    finally:
        cm.threading.Thread = orig

    assert e.fetches == 1
    assert e.posts and e.posts[0][0] == "/collect"


def test_explicit_network_off_overrides_production(monkeypatch):
    _clear_native(monkeypatch)
    monkeypatch.setenv("SHIPEASY_ENV", "production")
    e = _CaptureEngine(api_key="k", base_url="https://e.x", is_network_enabled=False)
    e.init()
    e.track("u1", "purchase", {"amount": 9})
    assert e.fetches == 0
    assert e.posts == []


# ---------------------------------------------------------------------------
# Telemetry — default branching (reuses the existing disable_telemetry option)
# ---------------------------------------------------------------------------


def test_telemetry_off_by_default_in_dev(monkeypatch):
    _clear_native(monkeypatch)
    monkeypatch.setenv("SHIPEASY_ENV", "development")
    e = Engine(api_key="k", base_url="https://e.x")
    assert e._telemetry._disabled is True


def test_telemetry_on_by_default_in_production(monkeypatch):
    _clear_native(monkeypatch)
    monkeypatch.setenv("SHIPEASY_ENV", "production")
    e = Engine(api_key="k", base_url="https://e.x")
    assert e._telemetry._disabled is False


def test_explicit_telemetry_enabled_in_dev(monkeypatch):
    _clear_native(monkeypatch)
    monkeypatch.setenv("SHIPEASY_ENV", "development")
    # disable_telemetry=False forces it ON even in a dev env — but only when the
    # master network switch is also on (here via is_network_enabled=True).
    e = Engine(
        api_key="k",
        base_url="https://e.x",
        disable_telemetry=False,
        is_network_enabled=True,
    )
    assert e._telemetry._disabled is False


def test_network_off_forces_telemetry_off(monkeypatch):
    _clear_native(monkeypatch)
    monkeypatch.setenv("SHIPEASY_ENV", "production")
    # Even an explicit telemetry-on cannot punch through a disabled master switch.
    e = Engine(
        api_key="k",
        base_url="https://e.x",
        disable_telemetry=False,
        is_network_enabled=False,
    )
    assert e._telemetry._disabled is True


def test_configured_env_option_drives_default_when_no_native(monkeypatch):
    _clear_native(monkeypatch)
    # No native env var → the SDK's own env option decides.
    dev = Engine(api_key="k", base_url="https://e.x", env="dev")
    assert dev._network_enabled is False
    assert dev._telemetry._disabled is True
    prod = Engine(api_key="k", base_url="https://e.x", env="prod")
    assert prod._network_enabled is True
    assert prod._telemetry._disabled is False
