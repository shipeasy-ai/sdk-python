# Advanced

## Anonymous-id bucketing + middleware

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
# (or low-level: engine.get_flag("new_checkout", {}))
```

An explicit `user_id`/`anonymous_id` always wins. The id is also on the request
(`environ["shipeasy.anon_id"]`). The cookie is non-`HttpOnly` by design so the
browser SDK buckets identically; a request with **no** unit still resolves a
fully-rolled (100%) gate as on. Cookie name + format are a cross-SDK contract.

## Private attributes

Pass `private_attributes` to the `Engine` to strip the named keys from every
outbound event `properties` bag before it POSTs to `/collect` (LD/Statsig
`privateAttributes`). The server evaluates locally, so private attrs **still
drive targeting** — they just never leave the process on the telemetry path:

```python
from shipeasy import Engine

engine = Engine(api_key="sdk_server_...", private_attributes=["email", "ssn"])
```

## Sticky bucketing

Pass a `sticky_store` to the `Engine` to pin a user's experiment assignment
across allocation changes. `InMemoryStickyStore` is built in; implement the
`StickyBucketStore` protocol (`get(unit)` / `set(unit, exp, entry)`) for a
durable backend:

```python
from shipeasy import Engine, InMemoryStickyStore

engine = Engine(api_key="sdk_server_...", sticky_store=InMemoryStickyStore())
```

Absent a store, bucketing is deterministic (MurmurHash3 over the unit).

## Bucketing unit (`bucketBy`)

The bucketing unit per experiment is **server-driven**: an experiment can be
configured to bucket on a non-default attribute (e.g. `company_id`) in the
dashboard, and the SDK reads it from the experiment definition
(`exp.bucketBy`) — falling back to `user_id` then `anonymous_id`. Make sure that
attribute is present in the user map you pass.

## Manual exposure — `log_exposure`

The server is stateless and never auto-logs exposures. Call `log_exposure` at the
real decision point (when you actually present the treatment) for parity with the
browser's auto-exposure. It re-evaluates the experiment and, if the user is
enrolled, POSTs a single `exposure` event.

The bound `Client` is the primary path — the same handle you read the experiment
with, no user argument:

```python
client = shipeasy.Client(current_user)
client.log_exposure("checkout_button")
```

The low-level `Engine` form takes the user explicitly:

```python
engine.log_exposure("u_123", "checkout_button")
# or with a full user dict:
engine.log_exposure({"user_id": "u_123", "country": "US"}, "checkout_button")
```

No-op in test mode or when the user isn't enrolled.

## Server-side rendering (SSR)

Emit the request's evaluated flags as a declarative `<script>` tag so the
browser SDK has them on first paint. `bootstrap_script_tag` carries the payload
in `data-*` attributes (**no key**); the static `se-bootstrap.js` loader
hydrates `window.__SE_BOOTSTRAP` and writes the `__se_anon_id` cookie so the
browser buckets identically to the server.

```python
user = {"user_id": "u_123"}

# Two tags for the document <head>. The PUBLIC client key (not the server key)
# goes on the i18n loader tag.
head = engine.bootstrap_script_tag(user, anon_id=anon_id) \
     + engine.i18n_script_tag(client_key, "en:prod")

# …or get the raw payload ({"flags", "configs", "experiments", "killswitches"}):
boot = engine.evaluate(user)
```

`bootstrap_script_tag` also accepts `i18n_profile=` and `base_url=`.
