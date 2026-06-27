# shipeasy (Python)

Server SDK for [Shipeasy](https://shipeasy.dev) — feature flags, remote configs, A/B experiments, and metric tracking. Server-key only, never embed in browsers.

```bash
pip install shipeasy
```

**Documentation:** [Installation & configuration](docs/pages/installation.md) · [full docs](docs/)

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

client.log_exposure("checkout_button")     # at the decision point
client.track("purchase", {"amount": 49})   # on conversion
```

`configure()` is first-config-wins and kicks off a one-shot fetch fire-and-forget,
so the first `Client(user).get_flag(...)` resolves against real rules. For a
long-running server that should keep the blob fresh, pass `poll=True` to start the
background poll — no lower-level object to manage:

```python
shipeasy.configure(api_key="sdk_server_...", poll=True)  # background poll
```

If your user object is already the attribute map, omit `attributes` (the default
is identity):

```python
shipeasy.configure(api_key="sdk_server_...")
shipeasy.Client({"user_id": "u_123", "country": "US"}).get_flag("new_checkout")
```

Constructing `Client(user)` before `configure()` raises `RuntimeError`.

### The bound `Client`

Everything per request is on `Client(user)` — no user argument on any call:
`get_flag` / `get_flag_detail` / `get_config` / `get_killswitch` /
`get_experiment`, plus `log_exposure(experiment_name)` and
`track(event, properties=None)`. So an experiment is end-to-end Client-only.

For unit tests and offline evaluation, swap `configure()` for its drop-in
siblings — [`configure_for_testing` / `configure_for_offline`](docs/pages/testing.md)
(below).

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
```

An explicit `user_id`/`anonymous_id` always wins. The id is also on the request
(`environ["shipeasy.anon_id"]`). The cookie is non-`HttpOnly` by design so the
browser SDK buckets identically; a request with **no** unit still resolves a
fully-rolled (100%) gate as on. Cookie name + format are a cross-SDK contract —
see `18-identity-bucketing.md`.

## Server-side rendering (SSR)

Emit the request's evaluated flags as a declarative `<script>` tag so the
browser SDK has them on first paint. `shipeasy.bootstrap_script_tag` carries the
payload in `data-*` attributes (**no key**); the static `se-bootstrap.js` loader
hydrates `window.__SE_BOOTSTRAP` and writes the `__se_anon_id` cookie so the
browser buckets identically to the server. The tag helpers are package-level and
delegate to the engine you set up with `configure()`.

```python
import shipeasy

user = {"user_id": "u_123"}

# Two tags for the document <head>. The PUBLIC client key (not the server
# key) goes on the i18n loader tag.
head = shipeasy.bootstrap_script_tag(user, anon_id=anon_id) \
     + shipeasy.i18n_script_tag(client_key, "en:prod")
```

`bootstrap_script_tag` also accepts `i18n_profile=` and `base_url=`
(defaults to `https://cdn.shipeasy.ai`).

## Default values

`get_flag` and `get_config` take a `default` that is returned only when the
value **cannot be evaluated** — never when it simply resolves off:

```python
client = shipeasy.Client(current_user)

# default is returned only if Shipeasy isn't ready yet OR the gate isn't in the
# blob. A gate that evaluates to False returns False, not the default.
client.get_flag("new_checkout", default=True)

# default is returned when the config key is absent (or decode raises).
client.get_config("billing_copy", default={"title": "Welcome"})
client.get_config("limits", decode=lambda v: v["max"], default=0)
```

## Evaluation detail

`get_flag_detail` returns a `FlagDetail(value, reason)` so you can log *why* a
flag resolved the way it did. `reason` is one of the exported constants:

```python
from shipeasy import (
    FlagDetail, CLIENT_NOT_READY, FLAG_NOT_FOUND, OFF, OVERRIDE, RULE_MATCH, DEFAULT,
)

d = shipeasy.Client(current_user).get_flag_detail("new_checkout")
print(d.value, d.reason)  # e.g. True RULE_MATCH
```

| reason | meaning |
| --- | --- |
| `OVERRIDE` | a `configure_for_testing` override forced the value |
| `CLIENT_NOT_READY` | the first fetch hasn't completed yet → `value=False` |
| `FLAG_NOT_FOUND` | no gate by that name in the blob → `value=False` |
| `OFF` | the gate exists but is disabled → `value=False` |
| `RULE_MATCH` | evaluated **on** (targeting + rollout) |
| `DEFAULT` | evaluated **off** (fell through) |

`get_flag` delegates to `get_flag_detail` and returns `.value` (substituting
`default` for `CLIENT_NOT_READY`/`FLAG_NOT_FOUND`).

## Change listeners

Register a callback fired after a background poll (`configure(poll=True)`) fetches
**new** data (a 200, not a 304). It returns an unsubscribe callable.

```python
unsubscribe = shipeasy.on_change(lambda: print("flags changed, rebuild cache"))
...
unsubscribe()  # stop listening
```

## Testing

Use `configure_for_testing()` — the test-mode sibling of `configure()`. It does
**zero network**, needs no api_key, and seeds the values your code under test
should see via override args. Read them through the ordinary `Client`:

```python
import shipeasy

shipeasy.configure_for_testing(
    flags={"new_checkout": True},
    configs={"billing_copy": {"title": "Welcome"}},
    experiments={"checkout_button": ("treatment", {"color": "green"})},
)

client = shipeasy.Client({"user_id": "u_123"})
assert client.get_flag("new_checkout") is True
assert client.get_config("billing_copy") == {"title": "Welcome"}
result = client.get_experiment("checkout_button", default_params={"color": "blue"})
assert result.in_experiment and result.group == "treatment"

# track()/log_exposure() are no-ops in test mode
client.track("purchase", {"amount": 49})
```

`configure_for_testing()` **replaces** any prior configuration, so each test
reconfigures freely.

## Offline snapshot

Run fully offline from a JSON snapshot — handy for local dev or air-gapped CI.
Use `configure_for_offline()`: evaluations run the **real** eval logic against
the snapshot; no network is touched, and override args still apply on top.

```python
import shipeasy

# From a file: { "flags": <body of /sdk/flags>, "experiments": <body of /sdk/experiments> }
shipeasy.configure_for_offline(path="shipeasy-snapshot.json")

# Or from in-memory blobs, with optional overrides on top
shipeasy.configure_for_offline(
    snapshot={
        "flags": {"gates": {...}, "configs": {...}},
        "experiments": {"experiments": {...}, "universes": {...}},
    },
    flags={"new_checkout": True},
)

shipeasy.Client({"user_id": "u_123"}).get_flag("new_checkout")
```

## Evaluation

Tested against the cross-language MurmurHash3 vectors in `experiment-platform/04-evaluation.md`.
