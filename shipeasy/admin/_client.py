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
    ApiClient,
    Configuration,
    FlagsApi,
    KillswitchApi,
    OpsApi,
)

# Friendly attribute name -> generated Api class.
#
# This is the LEAN admin surface: the vendored spec is the dedicated server-SDK
# contract (marketplace/openapi/spec/openapi-sdk.yaml in the monorepo), seven
# operations across three capabilities — file a public ticket, toggle a kill
# switch, manage a flag's whitelist. The full admin API (experiments, metrics,
# events, configs, i18n, projects, …) is intentionally NOT here; reach it through
# the Shipeasy CLI or MCP, which consume the complete spec.
_APIS = {
    "flags": FlagsApi,
    "killswitch": KillswitchApi,
    "ops": OpsApi,
}


class AdminClient:
    """Programmatic client for the Shipeasy **Admin** REST API.

    Authenticate with an admin SDK key (``sdk_admin_…``) and scope requests to a
    project. Each resource group is exposed as a lazily-constructed attribute
    whose methods map 1:1 to the OpenAPI operations::

        from shipeasy.admin import AdminClient

        admin = AdminClient(api_key=os.environ["SHIPEASY_ADMIN_KEY"],
                            project_id=os.environ["SHIPEASY_PROJECT_ID"])
        admin.ops.create_public_bug({"title": "Checkout 500s on Safari"})
        admin.killswitch.toggle_killswitch("payments.checkout", {})
        admin.flags.add_to_gate_whitelist("new_checkout", {"entries": ["alice@acme.dev"]})

    Three resource groups are available — ``flags``, ``killswitch`` and ``ops``.
    The rest of the admin API is reachable through the Shipeasy CLI or MCP.

    Two of the seven operations — ``ops.create_public_bug`` and
    ``ops.create_public_feature_request`` — are the PUBLIC ticket intake. They
    live on the Shipeasy edge worker and authenticate with a **client** key
    (``X-SDK-Key``), not the admin key, so pass ``client_key`` if you want to
    call them. The generated client routes them to the edge host on its own.

    :param api_key: Admin SDK key sent as ``Authorization: Bearer <api_key>``.
    :param project_id: Optional project id sent as the ``X-Project-Id`` header on
        every request (the per-request scoping the API expects). Operations also
        accept an explicit ``x_project_id`` argument to override per call.
    :param host: Admin API base URL. Defaults to ``https://shipeasy.ai`` (the
        spec's production server); point it at ``http://localhost:3000`` for
        local dev. The public intake ignores this — it has its own server list;
        pass ``_host_index=1`` on those calls to hit a local ``wrangler dev``.
    :param client_key: Client SDK key (``sdk_client_…``) carrying the
        ``tickets:public_create`` scope, sent as ``X-SDK-Key`` on the two public
        ticket operations. Optional — omit it if you only use the admin ones.
    """

    def __init__(
        self,
        api_key: str,
        *,
        project_id: Optional[str] = None,
        host: str = "https://shipeasy.ai",
        client_key: Optional[str] = None,
    ) -> None:
        config = Configuration(host=host, access_token=api_key)
        if client_key:
            config.api_key["clientSdkKey"] = client_key
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
