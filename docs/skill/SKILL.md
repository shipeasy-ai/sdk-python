---
name: shipeasy-python
description: Use Shipeasy (feature flags, configs, kill switches, A/B experiments, i18n) from Python. Covers configure() + Client(user), get_flag/get_config/get_experiment, track, testing, OpenFeature.
---

# Shipeasy Python SDK

Server SDK (`pip install shipeasy`, `import shipeasy`). Server-key only — never
embed in a browser. Requires Python 3.8+.

## Configure once

```python
import shipeasy

shipeasy.configure(
    api_key="sdk_server_...",
    attributes=lambda u: {"user_id": u.id, "country": u.country, "plan": u.plan},
)
```

`configure()` builds one shared `Engine` and returns it. Omit `attributes` if
your user object is already the attribute map.

## Evaluate (bound `Client(user)`)

Bind the user once per request, then call without re-passing it:

```python
client = shipeasy.Client(current_user)

client.get_flag("new_checkout")                 # bool; default= only on un-evaluable
client.get_config("billing_copy", default={})   # typed JSON; default= on absent
client.get_killswitch("payments_breaker")       # bool kill switch

result = client.get_experiment("checkout_button", default_params={"color": "blue"})
result.in_experiment, result.group, result.params
```

`get_flag_detail` returns `FlagDetail(value, reason)` (reasons: `RULE_MATCH`,
`DEFAULT`, `OFF`, `OVERRIDE`, `FLAG_NOT_FOUND`, `CLIENT_NOT_READY`).

## Low-level Engine + track

`Engine` takes the user on each call and owns `track()`:

```python
from shipeasy import Engine

engine = Engine(api_key="sdk_server_...")
engine.init()  # background poll; init_once() for serverless

engine.get_flag("new_checkout", {"user_id": "u_123"})
engine.track("u_123", "purchase", {"amount": 49})   # conversion event
```

## Testing (no network)

```python
from shipeasy import Engine

engine = Engine.for_testing()
engine.override_flag("new_checkout", True)
engine.override_config("billing_copy", {"title": "Welcome"})
engine.override_experiment("checkout_button", group="treatment", params={"color": "green"})
assert engine.get_flag("new_checkout", {"user_id": "u_123"}) is True
engine.clear_overrides()
```

Offline: `Engine.from_file(path)` / `Engine.from_snapshot(flags=..., experiments=...)`.

## OpenFeature

```python
from openfeature import api                       # pip install "shipeasy[openfeature]"
from shipeasy import Engine
from shipeasy.openfeature import ShipeasyProvider

engine = Engine(api_key="sdk_server_..."); engine.init()
api.set_provider(ShipeasyProvider(engine))
```

Boolean → gate; string/int/float/object → config.

## Error reporting — see()

```python
from shipeasy import see
try:
    charge(order)
except PaymentError as e:
    see(e).causes_the("checkout").to("use the backup processor")
```

## Other surfaces

- Anon bucketing: `AnonIdMiddleware` (WSGI) / `AnonIdASGIMiddleware` (ASGI) mint
  the shared `__se_anon_id` cookie; anonymous `get_flag` then just works.
- `Engine(private_attributes=[...])` strips keys from outbound events.
- `Engine(sticky_store=InMemoryStickyStore())` pins experiment assignment.
- `engine.log_exposure(user_or_id, exp_name)` for manual exposure.
- SSR: `engine.bootstrap_script_tag(user)` + `engine.i18n_script_tag(client_key, "en:prod")`.

## i18n

No server-side `t()`. The browser's Shipeasy **client** SDK renders labels; this
server SDK only emits the loader tag (public client key) during SSR.
