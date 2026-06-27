"""Tests for the configure() siblings that replace direct Engine construction:
``configure_for_testing`` and ``configure_for_offline``. Both wire up the
package-global engine so ``shipeasy.Client(user)`` reads against them — the docs
never construct an ``Engine`` directly.
"""
import json

import pytest

import shipeasy
from shipeasy import (
    Client,
    configure_for_offline,
    configure_for_testing,
    reset_global,
)


@pytest.fixture(autouse=True)
def _clean_global():
    reset_global()
    yield
    reset_global()


def test_configure_for_testing_seeds_overrides():
    shipeasy.configure_for_testing(
        flags={"new_checkout": True},
        configs={"copy": {"title": "Hi"}},
        experiments={"exp": ("treatment", {"color": "red"})},
    )
    client = Client({"user_id": "u_1"})
    assert client.get_flag("new_checkout") is True
    assert client.get_config("copy") == {"title": "Hi"}
    result = client.get_experiment("exp", {"color": "blue"})
    assert result.in_experiment is True
    assert result.group == "treatment"
    assert result.params == {"color": "red"}


def test_configure_for_testing_no_network_and_default_off():
    shipeasy.configure_for_testing()
    client = Client({"user_id": "u_1"})
    # Unseeded flag → its caller default, never a network call.
    assert client.get_flag("unknown", default=False) is False
    assert client.get_flag("unknown", default=True) is True


def test_configure_for_testing_replaces_so_tests_can_reconfigure():
    shipeasy.configure_for_testing(flags={"a": True})
    assert Client({"user_id": "u"}).get_flag("a") is True
    # Re-running replaces the global (configure() would have been first-wins).
    shipeasy.configure_for_testing(flags={"a": False})
    assert Client({"user_id": "u"}).get_flag("a") is False


def test_configure_for_testing_runs_attributes_transform():
    seen = {}

    def attrs(u):
        seen["called"] = True
        return {"user_id": u["id"]}

    shipeasy.configure_for_testing(attributes=attrs, flags={"f": True})
    assert Client({"id": "u_9"}).get_flag("f") is True
    assert seen.get("called") is True


def test_configure_for_offline_from_snapshot_evaluates_real_rules():
    snapshot = {
        "flags": {
            "gates": {
                "g": {"enabled": True, "rolloutPct": 10000, "salt": "s", "rules": []}
            },
            "configs": {},
        },
        "experiments": {},
    }
    shipeasy.configure_for_offline(snapshot=snapshot)
    # Real eval against the snapshot: a fully-rolled gate is on for a unit.
    assert Client({"user_id": "u_1"}).get_flag("g") is True


def test_configure_for_offline_from_file(tmp_path):
    blob = {
        "flags": {"gates": [], "configs": []},
        "experiments": {"experiments": [], "universes": []},
    }
    p = tmp_path / "snap.json"
    p.write_text(json.dumps(blob))
    shipeasy.configure_for_offline(path=str(p), flags={"forced": True})
    assert Client({"user_id": "u"}).get_flag("forced") is True


def test_configure_for_offline_requires_a_source():
    with pytest.raises(ValueError):
        configure_for_offline()


def test_package_helpers_require_configure():
    with pytest.raises(RuntimeError):
        shipeasy.on_change(lambda: None)
    with pytest.raises(RuntimeError):
        shipeasy.i18n_script_tag("clt_key")


def test_i18n_script_tag_delegates_to_global():
    shipeasy.configure_for_testing()
    tag = shipeasy.i18n_script_tag("clt_pub", "en:prod")
    assert "<script" in tag and "clt_pub" in tag


def test_configure_for_offline_and_testing_are_exported():
    assert hasattr(shipeasy, "configure_for_testing")
    assert hasattr(shipeasy, "configure_for_offline")
    assert "configure_for_testing" in shipeasy.__all__
    assert "configure_for_offline" in shipeasy.__all__


def test_on_the_spot_override_helpers():
    shipeasy.configure_for_testing(flags={"a": True})
    assert Client({"user_id": "u"}).get_flag("a") is True

    # flip on the spot, no reconfigure
    shipeasy.override_flag("a", False)
    shipeasy.override_config("copy", {"title": "Hi"})
    shipeasy.override_experiment("exp", "treatment", {"color": "green"})

    client = Client({"user_id": "u"})
    assert client.get_flag("a") is False
    assert client.get_config("copy") == {"title": "Hi"}
    r = client.get_experiment("exp", {"color": "blue"})
    assert r.in_experiment and r.group == "treatment" and r.params == {"color": "green"}

    # clear_overrides() drops EVERY override — including the seed from
    # configure_for_testing (test mode has no underlying blob), so "a" is gone.
    shipeasy.clear_overrides()
    assert Client({"user_id": "u"}).get_flag("a") is False
    # for offline, clearing reverts to the snapshot rather than to empty:
    shipeasy.configure_for_offline(
        snapshot={
            "flags": {
                "gates": {
                    "g": {"enabled": True, "rolloutPct": 10000, "salt": "g", "rules": []}
                },
                "configs": {},
            },
            "experiments": {},
        }
    )
    shipeasy.override_flag("g", False)
    assert Client({"user_id": "u"}).get_flag("g") is False
    shipeasy.clear_overrides()
    assert Client({"user_id": "u"}).get_flag("g") is True  # back to the snapshot


def test_override_helpers_require_configure():
    with pytest.raises(RuntimeError):
        shipeasy.override_flag("a", True)
    with pytest.raises(RuntimeError):
        shipeasy.clear_overrides()


def test_documented_snapshot_shape_evaluates():
    """The exact snapshot shape documented in docs/pages/testing.md must work."""
    snapshot = {
        "flags": {
            "gates": {
                "new_checkout": {
                    "enabled": True,
                    "rolloutPct": 10000,
                    "salt": "new_checkout",
                    "rules": [],
                },
                "beta_banner": {
                    "enabled": False,
                    "rolloutPct": 0,
                    "salt": "beta_banner",
                    "rules": [],
                },
            },
            "configs": {"billing_copy": {"value": {"title": "Welcome back"}}},
            "killswitches": {"payments_circuit_breaker": {"value": False}},
        },
        "experiments": {"experiments": {}, "universes": {}},
    }
    shipeasy.configure_for_offline(snapshot=snapshot)
    client = Client({"user_id": "u_1"})
    assert client.get_flag("new_checkout") is True
    assert client.get_flag("beta_banner") is False
    assert client.get_config("billing_copy") == {"title": "Welcome back"}
    assert client.get_killswitch("payments_circuit_breaker") is False
