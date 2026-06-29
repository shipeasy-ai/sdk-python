# Admin API client (optional) — `shipeasy.admin`

The base SDK *evaluates* flags, configs, and experiments
([`configure()`](configuration.md) + `shipeasy.Client(user)`). The **Admin API
client** is a separate, optional surface for *administering* those resources from
server code — creating gates, starting experiments, managing configs, kill
switches, universes, metrics, events, and more.

It is **off by default**: the base SDK never imports it, and its dependencies are
only pulled in when you opt in.

```bash
pip install "shipeasy[admin]"
```

The client is **generated from the Shipeasy OpenAPI spec**, so it is a raw, 1:1
projection of the REST API: id-based, basis-points, `snake_case`. It does *not*
add the name→id resolution or percent→basis-point conveniences you get from the
Shipeasy CLI/MCP — reach for those tools when you want the ergonomic surface, and
for this client when you want a typed, programmatic mirror of the API.

## Authenticate and scope

Mint an **admin** SDK key (`sdk_admin_…`) and scope every call to a project.

```python
import os
from shipeasy.admin import AdminClient

admin = AdminClient(
    api_key=os.environ["SHIPEASY_ADMIN_KEY"],   # Authorization: Bearer <key>
    project_id=os.environ["SHIPEASY_PROJECT_ID"],  # sent as X-Project-Id on every call
    # host defaults to https://shipeasy.ai; point at http://localhost:3000 for local dev
)
```

`project_id` is sent as the `X-Project-Id` header on every request. It is
optional on the constructor — individual operations also accept an explicit
`x_project_id` argument to override per call.

## Resource groups

Each resource group is a lazily-constructed attribute whose methods map 1:1 to
the OpenAPI operations:

```python
# list and create gates
gates = admin.gates.list_gates()
admin.gates.create_gate(...)

# start an experiment
admin.experiments.create_experiment(...)
admin.experiments.start_experiment(...)
```

Available groups: `gates`, `configs`, `killswitches`, `experiments`, `universes`,
`metrics`, `events`, `alert_rules`, `attributes`, `projects`, `ops`, `i18n`.

The exact method names, request models, and response shapes come straight from
the spec — explore them with `dir(admin.gates)` or your editor's autocomplete,
and the request/response types under `shipeasy.admin.generated.models`.

## Escape hatch

`admin.api_client` exposes the underlying generated `ApiClient` for advanced use
(custom headers, retries, a shared connection pool).

## Regenerating

The generated code lives under `shipeasy/admin/generated/` and is committed. When
the API contract changes, refresh the vendored spec and regenerate — only the
generated subpackage is rewritten, never the `AdminClient` shim:

```bash
cp <monorepo>/packages/openapi/openapi.json admin/openapi.json
bash scripts/gen_admin.sh
```

The generator version is pinned in `openapitools.json`.
