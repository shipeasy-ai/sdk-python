"""Tests for the OpenFeature provider (shipeasy.openfeature.ShipeasyProvider).

Drives the provider through the REAL openfeature-sdk (api.set_provider +
api.get_client). Flags/configs are seeded with the SDK's offline test
facilities (Client.from_snapshot / override_*), so nothing touches the network.
"""
import pytest

openfeature = pytest.importorskip("openfeature")

from openfeature import api
from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import ErrorCode
from openfeature.flag_evaluation import Reason

from shipeasy import Client
from shipeasy.openfeature import ShipeasyProvider


# A snapshot blob: a fully-on gate, a rollout-0 gate (evaluates False → DEFAULT),
# a disabled gate, and a set of typed configs.
SNAPSHOT_FLAGS = {
    "gates": {
        "on_gate": {"enabled": 1, "salt": "s", "rolloutPct": 10000},
        "off_rollout": {"enabled": 1, "salt": "s", "rolloutPct": 0},
        "disabled_gate": {"enabled": 0, "salt": "s", "rolloutPct": 10000},
    },
    "configs": {
        "str_cfg": {"value": "hello"},
        "int_cfg": {"value": 42},
        "float_cfg": {"value": 3.5},
        "obj_cfg": {"value": {"k": "v"}},
        "wrong_type": {"value": "not-an-int"},
    },
}


@pytest.fixture
def of_client():
    client = Client.from_snapshot(SNAPSHOT_FLAGS, {})
    api.set_provider(ShipeasyProvider(client))
    yield api.get_client()
    api.clear_providers()


def _ctx(uid="u1"):
    return EvaluationContext(targeting_key=uid)


# -- metadata ----------------------------------------------------------------


def test_metadata_name():
    provider = ShipeasyProvider(Client.for_testing())
    assert provider.get_metadata().name == "shipeasy"


# -- boolean: each type + reason mapping -------------------------------------


def test_boolean_targeting_match(of_client):
    d = of_client.get_boolean_details("on_gate", False, _ctx())
    assert d.value is True
    assert d.reason == Reason.TARGETING_MATCH


def test_boolean_default_reason_when_rolled_off(of_client):
    # Gate present + enabled but rollout 0% → evaluates False → reason DEFAULT.
    d = of_client.get_boolean_details("off_rollout", False, _ctx())
    assert d.value is False
    assert d.reason == Reason.DEFAULT


def test_boolean_disabled_reason(of_client):
    d = of_client.get_boolean_details("disabled_gate", True, _ctx())
    assert d.value is False
    assert d.reason == Reason.DISABLED


def test_boolean_flag_not_found(of_client):
    d = of_client.get_boolean_details("nope", True, _ctx())
    # Missing gate → ERROR/FLAG_NOT_FOUND, returns the default.
    assert d.value is True
    assert d.reason == Reason.ERROR
    assert d.error_code == ErrorCode.FLAG_NOT_FOUND


def test_boolean_provider_not_ready():
    # A client that was never initialized → CLIENT_NOT_READY → PROVIDER_NOT_READY.
    client = Client(api_key="sdk_server_x", disable_telemetry=True)
    api.set_provider(ShipeasyProvider(client))
    try:
        of = api.get_client()
        d = of.get_boolean_details("on_gate", True, _ctx())
        assert d.value is True
        assert d.reason == Reason.ERROR
        assert d.error_code == ErrorCode.PROVIDER_NOT_READY
    finally:
        api.clear_providers()


def test_boolean_override_static_reason():
    client = Client.from_snapshot(SNAPSHOT_FLAGS, {})
    client.override_flag("on_gate", True)
    api.set_provider(ShipeasyProvider(client))
    try:
        of = api.get_client()
        d = of.get_boolean_details("on_gate", False, _ctx())
        assert d.value is True
        assert d.reason == Reason.STATIC
    finally:
        api.clear_providers()


# -- string / int / float / object configs ----------------------------------


def test_string_resolves(of_client):
    d = of_client.get_string_details("str_cfg", "fallback", _ctx())
    assert d.value == "hello"
    assert d.reason == Reason.TARGETING_MATCH


def test_integer_resolves(of_client):
    d = of_client.get_integer_details("int_cfg", 0, _ctx())
    assert d.value == 42
    assert d.reason == Reason.TARGETING_MATCH


def test_float_resolves(of_client):
    d = of_client.get_float_details("float_cfg", 0.0, _ctx())
    assert d.value == 3.5
    assert d.reason == Reason.TARGETING_MATCH


def test_object_resolves(of_client):
    d = of_client.get_object_details("obj_cfg", {}, _ctx())
    assert d.value == {"k": "v"}
    assert d.reason == Reason.TARGETING_MATCH


def test_config_absent_returns_default(of_client):
    d = of_client.get_string_details("missing_cfg", "fallback", _ctx())
    assert d.value == "fallback"
    assert d.reason == Reason.DEFAULT


def test_config_type_mismatch(of_client):
    # "not-an-int" requested as integer → TYPE_MISMATCH + default.
    d = of_client.get_integer_details("wrong_type", 7, _ctx())
    assert d.value == 7
    assert d.reason == Reason.ERROR
    assert d.error_code == ErrorCode.TYPE_MISMATCH


def test_bool_is_not_an_integer():
    # A bool config value must not satisfy an integer request (bool ⊂ int).
    client = Client.from_snapshot({"configs": {"b": {"value": True}}}, {})
    api.set_provider(ShipeasyProvider(client))
    try:
        of = api.get_client()
        d = of.get_integer_details("b", 9, _ctx())
        assert d.value == 9
        assert d.error_code == ErrorCode.TYPE_MISMATCH
    finally:
        api.clear_providers()
