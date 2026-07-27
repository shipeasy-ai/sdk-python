"""Tests for the optional Admin API client (`shipeasy.admin.AdminClient`).

The client is generated from the OpenAPI spec and only importable with the
`admin` extra installed (`pip install "shipeasy[admin]"`), so the whole module is
guarded with ``importorskip`` — CI stays green without the extra.
"""
import pytest

admin = pytest.importorskip("shipeasy.admin")

from shipeasy.admin import AdminClient


def _client():
    # No network: constructing the client only wires up Configuration/ApiClient.
    return AdminClient(
        api_key="sdk_admin_test",
        project_id="proj_123",
        host="http://localhost:3000",
    )


def test_admin_client_constructs_and_wires_auth_and_scope():
    client = _client()
    config = client.api_client.configuration
    assert config.access_token == "sdk_admin_test"
    assert config.host == "http://localhost:3000"
    # project scoping is sent as the X-Project-Id default header on every request.
    assert client.api_client.default_headers.get("X-Project-Id") == "proj_123"


def test_admin_client_exposes_resource_groups():
    client = _client()
    # The three groups of the lean admin surface. Exhaustive on purpose: a
    # change to the SDK spec that adds or drops a group must move this list too.
    assert type(client.flags).__name__ == "FlagsApi"
    assert type(client.killswitch).__name__ == "KillswitchApi"
    assert type(client.ops).__name__ == "OpsApi"
    assert not hasattr(client, "comments")
    # …and the seven operations it carries, likewise exhaustive.
    assert hasattr(client.ops, "create_public_bug")
    assert hasattr(client.ops, "create_public_feature_request")
    assert hasattr(client.killswitch, "toggle_killswitch")
    assert hasattr(client.flags, "get_gate_whitelist")
    assert hasattr(client.flags, "set_gate_whitelist")
    assert hasattr(client.flags, "add_to_gate_whitelist")
    assert hasattr(client.flags, "remove_from_gate_whitelist")
    # Lazily constructed but cached: same instance on repeat access.
    assert client.flags is client.flags


def test_admin_client_unknown_group_raises_attribute_error():
    client = _client()
    with pytest.raises(AttributeError):
        client.not_a_real_group  # noqa: B018


def test_client_key_wires_the_public_intake_scheme():
    # The two public ticket ops authenticate with a CLIENT key (X-SDK-Key) on the
    # edge worker, not the admin bearer — the shim must plumb it to the
    # generated `clientSdkKey` apiKey slot or those calls go out unauthenticated.
    plain = _client()
    assert "clientSdkKey" not in plain.api_client.configuration.api_key

    scoped = AdminClient(api_key="sdk_admin_test", client_key="sdk_client_test")
    assert scoped.api_client.configuration.api_key["clientSdkKey"] == "sdk_client_test"


def test_project_id_is_optional():
    client = AdminClient(api_key="sdk_admin_test")
    assert "X-Project-Id" not in client.api_client.default_headers
