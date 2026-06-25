# shipeasy (Python)

Server SDK for [Shipeasy](https://shipeasy.dev) — feature flags, remote configs, A/B experiments, and metric tracking. Server-key only, never embed in browsers.

```bash
pip install shipeasy
```

## Quick start — `configure()` once, then `Client(user)` per request

Configure the SDK once at process start with your server key and an optional
`attributes` transform (your user object → the Shipeasy attribute map). Then
construct a cheap, user-bound `Client(user)` per request — every call takes **no
user argument**, because the user is bound at construction.

```python
import shipeasy

# Once, at startup. `attributes` maps YOUR user object to the attribute map
# Shipeasy targets on. Omit it if your user object is already that map.
shipeasy.configure(
    api_key="sdk_server_...",
    attributes=lambda u: {"user_id": u.id, "country": u.country, "plan": u.plan},
)

# Per request — bind the user once, then ask without re-passing it.
client = shipeasy.Client(current_user)

if client.get_flag("new_checkout"):
    ...

config = client.get_config("billing_copy")

result = client.get_experiment("checkout_button", default_params={"color": "blue"})
print(result.in_experiment, result.group, result.params)
```

`configure()` builds a single shared `Engine` (first-config-wins) and kicks off a
one-shot fetch fire-and-forget, so the first `Client(user).get_flag(...)`
resolves against real rules. For a long-running server that wants the background
poll, pass `init=False` and call `init()` on the returned engine:

```python
engine = shipeasy.configure(api_key="sdk_server_...", init=False)
engine.init()  # background poll
```

If your user object is already the attribute map, omit `attributes` (the default
is identity):

```python
shipeasy.configure(api_key="sdk_server_...")
shipeasy.Client({"user_id": "u_123", "country": "US"}).get_flag("new_checkout")
```

Constructing `Client(user)` before `configure()` raises `RuntimeError`.

### Low-level: the `Engine` directly

`Client(user)` is a thin handle over an `Engine`. You can also use the engine
directly — it takes the user on each call and owns `track()`, `see()`, the
`override_*` setters, and the offline factories:

```python
from shipeasy import Engine

engine = Engine(api_key="sdk_server_...")
engine.init()  # background poll; use init_once() for serverless

if engine.get_flag("new_checkout", {"user_id": "u_123", "country": "US"}):
    ...

config = engine.get_config("billing_copy")

result = engine.get_experiment(
    "checkout_button",
    user={"user_id": "u_123"},
    default_params={"color": "blue"},
)
print(result.in_experiment, result.group, result.params)

engine.track("u_123", "purchase", {"amount": 49})
```

> **Breaking change in 0.8.0:** the heavyweight client class was renamed
> `Client` → `Engine`, and `Client` is now the lightweight user-bound handle
> above. Replace `Client(api_key=...)` with `Engine(api_key=...)` (and
> `Client.for_testing()`/`from_snapshot`/`from_file` with `Engine.*`), or adopt
> `configure()` + `Client(user)`.

## Anonymous visitors (zero-config bucketing)

For logged-out traffic you need a *stable* unit so a fractional rollout buckets
the same on the server and in the browser. The middleware mints a first-party
`__se_anon_id` cookie (shared with every Shipeasy SDK) for any request without
one; evaluations then **default to it** as `anonymous_id`, so `get_flag` on an
anonymous request just works — no per-call wiring.

```python
# WSGI (Flask, Django, ...)
from shipeasy.middleware import AnonIdMiddleware
app.wsgi_app = AnonIdMiddleware(app.wsgi_app)

# ASGI (FastAPI, Starlette)
from shipeasy.middleware import AnonIdASGIMiddleware
app.add_middleware(AnonIdASGIMiddleware)
```

```python
# logged-out request → buckets on the __se_anon_id cookie automatically
shipeasy.Client({}).get_flag("new_checkout")
# (or, low-level: engine.get_flag("new_checkout", {}))
```

An explicit `user_id`/`anonymous_id` always wins. The id is also on the request
(`environ["shipeasy.anon_id"]`). The cookie is non-`HttpOnly` by design so the
browser SDK buckets identically; a request with **no** unit still resolves a
fully-rolled (100%) gate as on. Cookie name + format are a cross-SDK contract —
see `18-identity-bucketing.md`.

## Server-side rendering (SSR)

Emit the request's evaluated flags as a declarative `<script>` tag so the
browser SDK has them on first paint. `bootstrap_script_tag` carries the payload
in `data-*` attributes (**no key**); the static `se-bootstrap.js` loader
hydrates `window.__SE_BOOTSTRAP` and writes the `__se_anon_id` cookie so the
browser buckets identically to the server.

```python
user = {"user_id": "u_123"}

# Two tags for the document <head>. The PUBLIC client key (not the server
# key) goes on the i18n loader tag.
head = engine.bootstrap_script_tag(user, anon_id=anon_id) \
     + engine.i18n_script_tag(client_key, "en:prod")

# …or get the raw payload ({"flags", "configs", "experiments", "killswitches"}):
boot = engine.evaluate(user)
```

`bootstrap_script_tag` also accepts `i18n_profile=` and `base_url=`
(defaults to `https://cdn.shipeasy.ai`).

## Default values

`get_flag` and `get_config` take a `default` that is returned only when the
value **cannot be evaluated** — never when it simply resolves off:

```python
# default is returned only if the engine isn't initialized OR the gate isn't
# in the blob. A gate that evaluates to False returns False, not the default.
# Bound:      shipeasy.Client(user).get_flag("new_checkout", default=True)
engine.get_flag("new_checkout", {"user_id": "u_123"}, default=True)

# default is returned when the config key is absent (or decode raises).
engine.get_config("billing_copy", default={"title": "Welcome"})
engine.get_config("limits", decode=lambda v: v["max"], default=0)
```

## Evaluation detail

`get_flag_detail` returns a `FlagDetail(value, reason)` so you can log *why* a
flag resolved the way it did. `reason` is one of the exported constants:

```python
from shipeasy import (
    FlagDetail, CLIENT_NOT_READY, FLAG_NOT_FOUND, OFF, OVERRIDE, RULE_MATCH, DEFAULT,
)

d = engine.get_flag_detail("new_checkout", {"user_id": "u_123"})
# Bound: d = shipeasy.Client(user).get_flag_detail("new_checkout")
print(d.value, d.reason)  # e.g. True RULE_MATCH
```

| reason | meaning |
| --- | --- |
| `OVERRIDE` | a local `override_flag` forced the value (no telemetry) |
| `CLIENT_NOT_READY` | `init()`/`init_once()` hasn't run yet → `value=False` |
| `FLAG_NOT_FOUND` | no gate by that name in the blob → `value=False` |
| `OFF` | the gate exists but is disabled → `value=False` |
| `RULE_MATCH` | evaluated **on** (targeting + rollout) |
| `DEFAULT` | evaluated **off** (fell through) |

`get_flag` delegates to `get_flag_detail` and returns `.value` (substituting
`default` for `CLIENT_NOT_READY`/`FLAG_NOT_FOUND`).

## Change listeners

Register a callback fired after a background poll fetches **new** data (a 200,
not a 304). It returns an unsubscribe callable. Listeners never fire in
test/offline mode.

```python
unsubscribe = engine.on_change(lambda: print("flags changed, rebuild cache"))
...
unsubscribe()  # stop listening
```

## Offline snapshot

Run fully offline from a JSON snapshot — handy for tests, local dev, or
air-gapped CI. Evaluations run the **real** eval logic against the snapshot;
no network is ever touched (`init()`/`init_once()`/`track()` are no-ops) and
`override_*` setters still apply on top.

```python
# From a file: { "flags": <body of /sdk/flags>, "experiments": <body of /sdk/experiments> }
engine = Engine.from_file("shipeasy-snapshot.json")

# Or from in-memory blobs
engine = Engine.from_snapshot(
    flags={"gates": {...}, "configs": {...}},
    experiments={"experiments": {...}, "universes": {...}},
)

engine.get_flag("new_checkout", {"user_id": "u_123"})
```

## Testing

Use `Engine.for_testing()` for unit tests: it does **zero network**, needs no
api_key, disables telemetry, and makes `init()`/`init_once()`/`track()` no-ops.
Seed every entity with the `override_*` setters (Statsig-style local overrides) —
an override always wins over whatever the engine would otherwise resolve.

```python
from shipeasy import Engine

engine = Engine.for_testing()  # no key, no network, immediately usable

# Flags
engine.override_flag("new_checkout", True)
assert engine.get_flag("new_checkout", {"user_id": "u_123"}) is True

# Configs (decode is optional and still applies)
engine.override_config("billing_copy", {"title": "Welcome"})
assert engine.get_config("billing_copy") == {"title": "Welcome"}
assert engine.get_config("billing_copy", decode=lambda v: v["title"]) == "Welcome"

# Experiments → ExperimentResult(in_experiment=True, group=..., params=...)
engine.override_experiment("checkout_button", group="treatment", params={"color": "green"})
result = engine.get_experiment(
    "checkout_button",
    user={"user_id": "u_123"},
    default_params={"color": "blue"},
)
assert result.in_experiment and result.group == "treatment"
assert result.params == {"color": "green"}

# track() is a no-op in test mode — safe to call, sends nothing
engine.track("u_123", "purchase", {"amount": 49})

# Reset between cases
engine.clear_overrides()
```

The same `override_*` / `clear_overrides()` setters also work on a normal
`Engine` if you want to pin a value in a live engine.

## Evaluation

Tested against the cross-language MurmurHash3 vectors in `experiment-platform/04-evaluation.md`.
