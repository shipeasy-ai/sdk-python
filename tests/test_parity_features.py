import json

from shipeasy import (
    Client,
    FlagDetail,
    CLIENT_NOT_READY,
    FLAG_NOT_FOUND,
    OFF,
    OVERRIDE,
    RULE_MATCH,
    DEFAULT,
)


# A gate that is enabled and fully rolled out → evaluates ON for any unit.
def _on_gate():
    return {"enabled": 1, "rolloutPct": 10000, "salt": "s", "rules": []}


# A gate that exists and is enabled but rolled out to 0% → evaluates OFF.
def _zero_gate():
    return {"enabled": 1, "rolloutPct": 0, "salt": "s", "rules": []}


def _disabled_gate():
    return {"enabled": 0, "rolloutPct": 10000, "salt": "s", "rules": []}


# ---------------------------------------------------------------------------
# Feature A — default on get_flag / get_config
# ---------------------------------------------------------------------------


def test_get_flag_default_returned_when_not_initialized():
    # A plain (un-init'd) client cannot evaluate → default is returned.
    client = Client(api_key="k", disable_telemetry=True)
    assert client.get_flag("any", {"user_id": "u1"}) is False
    assert client.get_flag("any", {"user_id": "u1"}, default=True) is True


def test_get_flag_default_returned_when_flag_not_found():
    client = Client.from_snapshot(flags={"gates": {}}, experiments={})
    assert client.get_flag("missing", {"user_id": "u1"}, default=True) is True


def test_get_flag_default_NOT_returned_when_flag_evaluates_false():
    # Flag IS found and evaluable but resolves False → return the real False,
    # NOT the default.
    client = Client.from_snapshot(flags={"gates": {"g": _zero_gate()}}, experiments={})
    assert client.get_flag("g", {"user_id": "u1"}, default=True) is False


def test_get_config_default_when_absent():
    client = Client.from_snapshot(flags={"configs": {}}, experiments={})
    assert client.get_config("missing") is None
    assert client.get_config("missing", default={"x": 1}) == {"x": 1}


def test_get_config_default_on_decode_failure():
    client = Client.from_snapshot(
        flags={"configs": {"c": {"value": {"n": 1}}}}, experiments={}
    )
    out = client.get_config("c", decode=lambda v: v["MISSING"], default="fallback")
    assert out == "fallback"


# ---------------------------------------------------------------------------
# Feature B — flag evaluation detail (all reasons)
# ---------------------------------------------------------------------------


def test_reason_override_short_circuits_before_telemetry():
    client = Client.for_testing()
    client.override_flag("g", True)
    d = client.get_flag_detail("g", {"user_id": "u1"})
    assert isinstance(d, FlagDetail)
    assert d.value is True and d.reason == OVERRIDE


def test_reason_client_not_ready():
    client = Client(api_key="k", disable_telemetry=True)  # not initialized
    d = client.get_flag_detail("g", {"user_id": "u1"})
    assert d.value is False and d.reason == CLIENT_NOT_READY


def test_reason_flag_not_found():
    client = Client.from_snapshot(flags={"gates": {}}, experiments={})
    d = client.get_flag_detail("missing", {"user_id": "u1"})
    assert d.value is False and d.reason == FLAG_NOT_FOUND


def test_reason_off_when_disabled():
    client = Client.from_snapshot(
        flags={"gates": {"g": _disabled_gate()}}, experiments={}
    )
    d = client.get_flag_detail("g", {"user_id": "u1"})
    assert d.value is False and d.reason == OFF


def test_reason_rule_match_when_on():
    client = Client.from_snapshot(flags={"gates": {"g": _on_gate()}}, experiments={})
    d = client.get_flag_detail("g", {"user_id": "u1"})
    assert d.value is True and d.reason == RULE_MATCH


def test_reason_default_when_evaluates_off():
    client = Client.from_snapshot(flags={"gates": {"g": _zero_gate()}}, experiments={})
    d = client.get_flag_detail("g", {"user_id": "u1"})
    assert d.value is False and d.reason == DEFAULT


def test_get_flag_delegates_to_detail():
    client = Client.from_snapshot(flags={"gates": {"g": _on_gate()}}, experiments={})
    assert client.get_flag("g", {"user_id": "u1"}) is True


def test_get_flag_detail_emits_gate_telemetry_once_not_on_override():
    calls = []
    client = Client.from_snapshot(flags={"gates": {"g": _on_gate()}}, experiments={})
    client._telemetry.emit = lambda feature, resource: calls.append((feature, resource))
    client.get_flag_detail("g", {"user_id": "u1"})
    assert calls == [("gate", "g")]
    # Override path must NOT emit telemetry.
    calls.clear()
    client.override_flag("g", False)
    client.get_flag_detail("g", {"user_id": "u1"})
    assert calls == []


# ---------------------------------------------------------------------------
# Feature C — change listeners
# ---------------------------------------------------------------------------


def test_on_change_fires_on_new_data_and_unsubscribe_works():
    client = Client(api_key="k", disable_telemetry=True)

    # Drive the apply path directly: alternate 200 (new data) then 304.
    responses = iter(
        [
            (200, {"ETag": "v1"}, json.dumps({"gates": {}}).encode()),  # flags 200
            (304, {}, b""),  # exps 304
            (304, {}, b""),  # flags 304
            (304, {}, b""),  # exps 304
        ]
    )

    def fake_get(path, etag):
        return next(responses)

    client._http_get = fake_get

    fired = []
    unsub = client.on_change(lambda: fired.append(1))

    # First poll: flags returned 200 → listener fires once.
    assert client._fetch_all() is True
    client._notify_change()
    assert fired == [1]

    # Unsubscribe, then a no-change poll: nothing fires.
    unsub()
    assert client._fetch_all() is False  # both 304
    client._notify_change()
    assert fired == [1]


def test_on_change_listener_error_is_isolated():
    client = Client(api_key="k", disable_telemetry=True)
    fired = []
    client.on_change(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    client.on_change(lambda: fired.append(1))
    # Must not raise; the good listener still runs.
    client._notify_change()
    assert fired == [1]


# ---------------------------------------------------------------------------
# Feature D — offline file / snapshot data source
# ---------------------------------------------------------------------------


def test_from_snapshot_evaluates_with_no_network():
    client = Client.from_snapshot(
        flags={"gates": {"g": _on_gate()}}, experiments={}
    )
    # init/init_once/track are no-ops (would raise on real network).
    client.init()
    client.init_once()
    client.track("u1", "evt")
    assert client.get_flag("g", {"user_id": "u1"}) is True
    # Overrides apply on top of the snapshot.
    client.override_flag("g", False)
    assert client.get_flag("g", {"user_id": "u1"}) is False


def test_from_file_loads_both_blobs(tmp_path):
    p = tmp_path / "snap.json"
    p.write_text(
        json.dumps(
            {
                "flags": {"gates": {"g": _on_gate()}, "configs": {"c": {"value": 7}}},
                "experiments": {},
            }
        )
    )
    client = Client.from_file(str(p))
    assert client.get_flag("g", {"user_id": "u1"}) is True
    assert client.get_config("c") == 7
