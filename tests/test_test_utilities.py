from shipeasy import Client, ExperimentResult


# Client.for_testing() builds a no-network, immediately-usable client: no api_key,
# telemetry disabled, init()/init_once()/track() never touch the network. Local
# overrides (Statsig-style) win over the (empty) blob in every getter.


def test_for_testing_needs_no_key_or_network():
    client = Client.for_testing()
    # No fetch happens — these are no-ops in test mode (would raise on network).
    client.init()
    client.init_once()
    # Getters resolve against the empty blob with no overrides.
    assert client.get_flag("anything", {"user_id": "u1"}) is False
    assert client.get_config("anything") is None
    result = client.get_experiment("anything", {"user_id": "u1"}, default_params={"k": 1})
    assert result.in_experiment is False


def test_override_flag_wins():
    client = Client.for_testing()
    client.override_flag("new_checkout", True)
    assert client.get_flag("new_checkout", {"user_id": "u1"}) is True
    client.override_flag("new_checkout", False)
    assert client.get_flag("new_checkout", {"user_id": "u1"}) is False


def test_override_config_returned_without_decode():
    client = Client.for_testing()
    client.override_config("billing_copy", {"title": "Hi"})
    assert client.get_config("billing_copy") == {"title": "Hi"}


def test_override_config_honors_decode():
    client = Client.for_testing()
    client.override_config("limits", {"max": 5})
    decoded = client.get_config("limits", decode=lambda v: v["max"] * 2)
    assert decoded == 10


def test_override_experiment_returns_in_experiment():
    client = Client.for_testing()
    client.override_experiment("checkout_button", group="treatment", params={"color": "green"})
    result = client.get_experiment(
        "checkout_button",
        user={"user_id": "u1"},
        default_params={"color": "blue"},
    )
    assert isinstance(result, ExperimentResult)
    assert result.in_experiment is True
    assert result.group == "treatment"
    assert result.params == {"color": "green"}


def test_clear_overrides_resets():
    client = Client.for_testing()
    client.override_flag("f", True)
    client.override_config("c", 42)
    client.override_experiment("e", group="t", params={"x": 1})
    client.clear_overrides()
    assert client.get_flag("f", {"user_id": "u1"}) is False
    assert client.get_config("c") is None
    assert client.get_experiment("e", {"user_id": "u1"}, default_params=None).in_experiment is False


def test_track_is_a_noop_in_test_mode():
    client = Client.for_testing()
    # Must not raise and must not spawn a network thread.
    client.track("u1", "purchase", {"amount": 49})


def test_overrides_work_on_a_normal_client():
    # The override setters are usable on a normal client too, not just for_testing().
    client = Client(api_key="sdk_server_x", disable_telemetry=True)
    client.override_flag("gate", True)
    assert client.get_flag("gate", {"user_id": "u1"}) is True
