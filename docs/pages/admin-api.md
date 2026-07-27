# Admin API client (optional) — `shipeasy.admin`

The base SDK *evaluates* flags, configs, and experiments
([`configure()`](configuration.md) + `shipeasy.Client(user)`). The **Admin API
client** is a separate, optional surface for *administering* a small, deliberate
slice of those resources from server code.

It is **intentionally lean** — three groups of operations, not the whole admin
API:

| Group                       | What it covers                                                     |
| --------------------------- | ------------------------------------------------------------------ |
| Public ticket queue         | File a bug or feature request, list the queue, read and update one item, and hold its comment thread |
| Kill-switch sub-switches    | Add, edit, and delete the named nested switches on a kill switch    |
| Flag whitelists             | Read a gate and manage the whitelist on its targeting stack         |

Everything else in the admin API — experiments, metrics, events, configs, i18n,
projects, connectors, keys — is deliberately **not** here. Reach for the Shipeasy
CLI or MCP for those; they speak the complete spec. Keeping the vendored contract
small is what keeps the generated client small.

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
# file a bug on the public ticket queue
admin.ops.create_ops_item(...)

# read one item and comment on it
item = admin.ops.get_ops_item("42")
admin.comments.create_ops_comment("42", ...)

# manage a gate's whitelist (it lives on the targeting stack)
gate = admin.flags.get_gate("g_123")
admin.flags.update_gate("g_123", ...)

# add or remove a kill switch's nested sub-switch
admin.killswitch.set_killswitch_switch("k_123", ...)
admin.killswitch.unset_killswitch_switch("k_123", ...)
```

Available groups: `flags`, `killswitch`, `ops`, `comments`. Any other attribute
raises `AttributeError` listing these four.

The exact method names, request models, and response shapes come straight from
the spec — explore them with `dir(admin.flags)` or your editor's autocomplete,
and the request/response types under `shipeasy.admin.generated.models`.

## Escape hatch

`admin.api_client` exposes the underlying generated `ApiClient` for advanced use
(custom headers, retries, a shared connection pool).

## Regenerating

The generated code lives under `shipeasy/admin/generated/` and is committed.
`admin/openapi.json` is **not** the full Shipeasy spec — it is the pruned subset
described above, produced in the monorepo by `scripts/sdk-spec/prune.mjs` from
`scripts/sdk-spec/keep-set.json`. Do not hand-edit it, and do not replace it with
the full `openapi.json`: that is what bloats the generated client back to
megabytes.

From the monorepo, re-vendor and regenerate in one step (only the generated
subpackage is rewritten, never the `AdminClient` shim):

```bash
pnpm sdk:spec:regen sdk-python
```

A monorepo pre-commit hook blocks any commit that changes the admin spec while
this vendored copy is stale, so the two cannot silently drift.

The generator version is pinned in `openapitools.json`.
