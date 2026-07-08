from shipeasy import Engine


# Engine.for_testing() builds a no-network, immediately-usable client: no api_key,
# telemetry disabled, init()/init_once()/track() never touch the network. Local
# overrides (Statsig-style) win over the (empty) blob in every getter.


def test_for_testing_needs_no_key_or_network():
    client = Engine.for_testing()
    # No fetch happens — these are no-ops in test mode (would raise on network).
    client.init()
    client.init_once()
    # Getters resolve against the empty blob with no overrides.
    assert client.get_flag("anything", {"user_id": "u1"}) is False
    assert client.get_config("anything") is None
    # No experiments loaded → not enrolled; get() falls back to the caller value.
    a = client.universe("anything").assign({"user_id": "u1"})
    assert a.enrolled is False
    assert a.get("k", 1) == 1


def test_override_flag_wins():
    client = Engine.for_testing()
    client.override_flag("new_checkout", True)
    assert client.get_flag("new_checkout", {"user_id": "u1"}) is True
    client.override_flag("new_checkout", False)
    assert client.get_flag("new_checkout", {"user_id": "u1"}) is False


def test_override_config_returned_without_decode():
    client = Engine.for_testing()
    client.override_config("billing_copy", {"title": "Hi"})
    assert client.get_config("billing_copy") == {"title": "Hi"}


def test_override_config_honors_decode():
    client = Engine.for_testing()
    client.override_config("limits", {"max": 5})
    decoded = client.get_config("limits", decode=lambda v: v["max"] * 2)
    assert decoded == 10


def _running_exp(universe="u", group="treatment", params=None):
    # A minimal running experiment in a real blob. A pure override needs a loaded
    # experiment to surface through universe(name).assign().
    return {
        "experiments": {
            "checkout_button": {
                "universe": universe,
                "status": "running",
                "salt": "s",
                "allocationPct": 10000,
                "groups": [{"name": group, "weight": 10000, "params": params or {}}],
            }
        },
        "universes": {universe: {}},
    }


def test_override_experiment_surfaces_through_assign():
    # A pure override wins over blob eval for an experiment already present +
    # running in the loaded blob. Seed a real blob, then layer the override.
    client = Engine.from_snapshot(flags={}, experiments=_running_exp())
    client.override_experiment("checkout_button", group="control", params={"color": "green"})
    a = client.universe("u").assign({"user_id": "u1"})
    assert a.enrolled is True
    assert a.group == "control"  # the override group wins over the blob's variant
    assert a.get("color") == "green"


def test_clear_overrides_resets():
    client = Engine.from_snapshot(flags={}, experiments=_running_exp())
    client.override_flag("f", True)
    client.override_config("c", 42)
    client.override_experiment("checkout_button", group="control", params={"color": "green"})
    # The override forces group "control" over the blob's variant.
    assert client.universe("u").assign({"user_id": "u1"}).group == "control"
    client.clear_overrides()
    assert client.get_flag("f", {"user_id": "u1"}) is False
    assert client.get_config("c") is None
    # Override dropped → blob eval decides (the real variant, not the forced one).
    a = client.universe("u").assign({"user_id": "u1"})
    assert a.enrolled is True
    assert a.group == "treatment"


def test_track_is_a_noop_in_test_mode():
    client = Engine.for_testing()
    # Must not raise and must not spawn a network thread.
    client.track("u1", "purchase", {"amount": 49})


def test_overrides_work_on_a_normal_client():
    # The override setters are usable on a normal client too, not just for_testing().
    client = Engine(api_key="sdk_server_x", disable_telemetry=True)
    client.override_flag("gate", True)
    assert client.get_flag("gate", {"user_id": "u1"}) is True
