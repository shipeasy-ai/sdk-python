"""The ``AdminClient`` entry point for the optional Admin API client.

This is the only hand-written file in :mod:`shipeasy.admin` — everything under
:mod:`shipeasy.admin.generated` is produced by ``scripts/gen_admin.sh`` from the
vendored OpenAPI spec and must not be edited by hand. ``AdminClient`` is a thin
auth/scoping wrapper over the generated ``ApiClient``; it does **not** add
name->id resolution or percent->basis-point conversion (that ergonomic facade
lives in the Shipeasy CLI/MCP, not here). The surface here is the raw,
1:1-with-the-spec REST API.
"""
from __future__ import annotations

from typing import Optional

from .generated import (
    AlertsApi,
    ApiClient,
    APIKeysApi,
    AttributesApi,
    Configuration,
    ConfigsApi,
    ConnectorsApi,
    DraftsApi,
    ErrorsApi,
    EventsApi,
    ExperimentsApi,
    FlagsApi,
    KeysApi,
    KillswitchApi,
    MetricsApi,
    OpsApi,
    ProfilesApi,
    ProjectsApi,
    UniversesApi,
)

# Friendly attribute name -> generated Api class. Mirrors the resource tags of
# the Admin API (and the CLI/MCP `release`/`metrics`/`events`/... groups).
_APIS = {
    "flags": FlagsApi,
    "configs": ConfigsApi,
    "killswitch": KillswitchApi,
    "experiments": ExperimentsApi,
    "universes": UniversesApi,
    "attributes": AttributesApi,
    "metrics": MetricsApi,
    "events": EventsApi,
    "ops": OpsApi,
    "alerts": AlertsApi,
    "projects": ProjectsApi,
    "profiles": ProfilesApi,
    "keys": KeysApi,
    "drafts": DraftsApi,
    "errors": ErrorsApi,
    "connectors": ConnectorsApi,
    "api_keys": APIKeysApi,
}


class AdminClient:
    """Programmatic client for the Shipeasy **Admin** REST API.

    Authenticate with an admin SDK key (``sdk_admin_…``) and scope requests to a
    project. Each resource group is exposed as a lazily-constructed attribute
    whose methods map 1:1 to the OpenAPI operations::

        from shipeasy.admin import AdminClient

        admin = AdminClient(api_key=os.environ["SHIPEASY_ADMIN_KEY"],
                            project_id=os.environ["SHIPEASY_PROJECT_ID"])
        admin.flags.list_gates()
        admin.experiments.create_experiment(...)

    :param api_key: Admin SDK key sent as ``Authorization: Bearer <api_key>``.
    :param project_id: Optional project id sent as the ``X-Project-Id`` header on
        every request (the per-request scoping the API expects). Operations also
        accept an explicit ``x_project_id`` argument to override per call.
    :param host: API base URL. Defaults to ``https://shipeasy.ai`` (the spec's
        production server); point it at ``http://localhost:3000`` for local dev.
    """

    def __init__(
        self,
        api_key: str,
        *,
        project_id: Optional[str] = None,
        host: str = "https://shipeasy.ai",
    ) -> None:
        config = Configuration(host=host, access_token=api_key)
        self._api_client = ApiClient(config)
        if project_id:
            self._api_client.set_default_header("X-Project-Id", project_id)
        self._cache: dict[str, object] = {}

    @property
    def api_client(self) -> ApiClient:
        """The underlying generated :class:`ApiClient` (advanced/escape hatch)."""
        return self._api_client

    def __getattr__(self, name: str):
        api_cls = _APIS.get(name)
        if api_cls is None:
            raise AttributeError(
                f"{type(self).__name__!r} object has no attribute {name!r}. "
                f"Available resource groups: {', '.join(sorted(_APIS))}."
            )
        cache = self.__dict__.setdefault("_cache", {})
        if name not in cache:
            cache[name] = api_cls(self.__dict__["_api_client"])
        return cache[name]

    def __dir__(self):
        return sorted(set(super().__dir__()) | set(_APIS))
