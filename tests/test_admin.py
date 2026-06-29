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
    # A representative slice of the 17 generated resource groups.
    assert type(client.flags).__name__ == "FlagsApi"
    assert type(client.experiments).__name__ == "ExperimentsApi"
    assert type(client.connectors).__name__ == "ConnectorsApi"
    assert type(client.errors).__name__ == "ErrorsApi"
    assert hasattr(client.flags, "list_gates")
    assert hasattr(client.experiments, "create_experiment")
    # Lazily constructed but cached: same instance on repeat access.
    assert client.flags is client.flags


def test_admin_client_unknown_group_raises_attribute_error():
    client = _client()
    with pytest.raises(AttributeError):
        client.not_a_real_group  # noqa: B018


def test_project_id_is_optional():
    client = AdminClient(api_key="sdk_admin_test")
    assert "X-Project-Id" not in client.api_client.default_headers
