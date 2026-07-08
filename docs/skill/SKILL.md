---
name: shipeasy-python
description: Use Shipeasy (feature flags, configs, kill switches, A/B experiments, i18n) from Python. Covers configure() + Client(user), get_flag/get_config/universe(name).assign(), track, testing, OpenFeature.
---

# Shipeasy Python SDK

Server SDK (`pip install shipeasy`, `import shipeasy`). Server-key only — never
embed in a browser. Requires Python 3.9+.

Two things only: **`configure()`** once at startup, then **`shipeasy.Client(user)`**
per request.

> **Pulling deeper docs.** Each section below links its full reference page and
> copy-paste snippets — fetch any of them as raw Markdown when you need more than
> this summary. Discover the whole tree from the manifest:
> `https://shipeasy-ai.github.io/sdk-python/manifest.json` (lists every
> `pages/<key>.md` and `snippets/<group>/<leaf>.md`). All URLs below are
> `https://shipeasy-ai.github.io/sdk-python/…`.

## Configure once

```python
import shipeasy

shipeasy.configure(
    api_key="sdk_server_...",
    attributes=lambda u: {"user_id": u.id, "country": u.country, "plan": u.plan},
)
```

Omit `attributes` if your user object is already the attribute map. For a
long-running server pass `poll=True` to keep the blob fresh in the background.

**Quiet outside production (0.17.0+).** By default the SDK makes NO outbound
request (no fetch, `track`, exposure, `see()`, or telemetry) unless it detects a
production environment — via `SHIPEASY_ENV`/`APP_ENV`/`ENV`/`PYTHON_ENV`
(`production`/`prod`), else the `env` option (default `"prod"`). On a dev machine
or in CI, set `SHIPEASY_ENV=production` or pass `is_network_enabled=True` to turn
egress back on; pass `is_network_enabled=False` to force fully offline.

**Django:** add `"shipeasy.django"` to `INSTALLED_APPS`, run
`python manage.py shipeasy_install` (idempotently wires the anon-id middleware +
a `SHIPEASY = {...}` settings block + `.env`), then set `SHIPEASY["SERVER_KEY"]`.
The app's AppConfig calls `configure()` from that dict at boot — no manual
`configure()` call needed.

→ More: `pages/installation.md` (per-framework setup, incl. the Django app),
`pages/configuration.md` (every option).

## Evaluate (bound `Client(user)`)

Bind the user once per request, then call without re-passing it — `assign` and
`track` are on the bound client too, so experiments are end-to-end here:

```python
client = shipeasy.Client(current_user)

client.get_flag("new_checkout")                 # bool; default= only on un-evaluable
client.get_config("billing_copy", default={})   # typed JSON; default= on absent
client.get_killswitch("payments_breaker")       # bool kill switch

# A universe is a mutual-exclusion pool: a unit lands in <=1 experiment.
# assign() auto-logs one exposure when enrolled; a.get() resolves
# variant override -> universe default -> fallback (works even when not enrolled).
a = client.universe("checkout").assign()
a.name, a.group, a.enrolled                     # None/None/False when not enrolled
a.get("color", "blue")

client.track("purchase", {"amount": 49})        # conversion / metric event
```

`get_flag_detail` returns `FlagDetail(value, reason)` (reasons: `RULE_MATCH`,
`DEFAULT`, `OFF`, `OVERRIDE`, `FLAG_NOT_FOUND`, `CLIENT_NOT_READY`).

→ More: pages `pages/flags.md` · `pages/configs.md` · `pages/killswitches.md`
(incl. named switches) · `pages/experiments.md`. Snippets
`snippets/release/{flags,configs,killswitches,experiments}.md` and
`snippets/metrics/track.md` (event tracking).

## Testing (no network)

Use the `configure()` siblings — seed overrides, read through the same `Client`:

```python
shipeasy.configure_for_testing(
    flags={"new_checkout": True},
    configs={"billing_copy": {"title": "Welcome"}},
)
assert shipeasy.Client({"user_id": "u_123"}).get_flag("new_checkout") is True

# flip a value on the spot, mid-test:
shipeasy.override_flag("new_checkout", False)
shipeasy.clear_overrides()
```

An `experiments={name: (group, params)}` override is a **pure override** — it wins
over blob eval but only surfaces through `universe(name).assign()` for an
experiment already in the loaded blob. Pair it with a real experiment blob offline:

```python
shipeasy.configure_for_offline(
    snapshot={"flags": {"gates": {}, "configs": {}},
              "experiments": {"experiments": {"exp": {"universe": "u", "status": "running",
                              "salt": "s", "allocationPct": 10000,
                              "groups": [{"name": "control", "weight": 10000, "params": {}}]}},
                              "universes": {"u": {}}}},
    experiments={"exp": ("treatment", {"color": "green"})},   # override wins over the variant
)
assert shipeasy.Client({"user_id": "u_123"}).universe("u").assign().group == "treatment"
```

Offline (real rules from a snapshot / file):

```python
shipeasy.configure_for_offline(path="snapshot.json")
# or snapshot={"flags": {...}, "experiments": {...}}, plus optional overrides
```

→ More: `pages/testing.md` (override helpers + a working example
`shipeasy-snapshot.json`).

## OpenFeature

```python
import shipeasy                                   # pip install "shipeasy[openfeature]"
from openfeature import api
from shipeasy.openfeature import ShipeasyProvider

shipeasy.configure(api_key="sdk_server_...", poll=True)
api.set_provider(ShipeasyProvider())             # uses the configured global
```

Boolean → gate; string/int/float/object → config.

→ More: `pages/openfeature.md` (reason mapping, type routing).

## Error reporting — see()

```python
from shipeasy import see
try:
    charge(order)
except PaymentError as e:
    see(e).causes_the("checkout").to("use the backup processor")
```

→ More: `pages/error-reporting.md` · snippets `snippets/ops/see.md`
(`.extras()`, violations, control-flow exceptions).

## Other surfaces

- Anon bucketing: `AnonIdMiddleware` (WSGI) / `AnonIdASGIMiddleware` (ASGI) mint
  the shared `__se_anon_id` cookie; anonymous `get_flag` then just works.
- `configure(private_attributes=[...])` strips keys from outbound events.
- `configure(sticky_store=InMemoryStickyStore())` pins experiment assignment.
- Exposure is automatic: an enrolled `client.universe(name).assign()` logs one
  deduped exposure — there is no manual `log_exposure`.
- SSR: `shipeasy.bootstrap_script_tag(user)` + `shipeasy.i18n_script_tag(client_key, "en:prod")`.

→ More: `pages/advanced.md`.

## i18n

No server-side `t()`. The browser's Shipeasy **client** SDK renders labels; this
server SDK only emits the loader tag (public client key) during SSR.

→ More: `pages/i18n.md` · snippets `snippets/i18n/setup.md`.
