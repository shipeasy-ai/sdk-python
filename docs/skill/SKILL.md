---
name: shipeasy-python
description: Use Shipeasy (feature flags, configs, kill switches, A/B experiments, i18n) from Python. Covers configure() + Client(user), get_flag/get_config/get_experiment, track, testing, OpenFeature.
---

# Shipeasy Python SDK

Server SDK (`pip install shipeasy`, `import shipeasy`). Server-key only — never
embed in a browser. Requires Python 3.8+.

Two things only: **`configure()`** once at startup, then **`shipeasy.Client(user)`**
per request.

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

## Evaluate (bound `Client(user)`)

Bind the user once per request, then call without re-passing it — `track` and
`log_exposure` are on the bound client too, so experiments are end-to-end here:

```python
client = shipeasy.Client(current_user)

client.get_flag("new_checkout")                 # bool; default= only on un-evaluable
client.get_config("billing_copy", default={})   # typed JSON; default= on absent
client.get_killswitch("payments_breaker")       # bool kill switch

result = client.get_experiment("checkout_button", default_params={"color": "blue"})
result.in_experiment, result.group, result.params

client.log_exposure("checkout_button")          # at the decision point
client.track("purchase", {"amount": 49})        # conversion event
```

`get_flag_detail` returns `FlagDetail(value, reason)` (reasons: `RULE_MATCH`,
`DEFAULT`, `OFF`, `OVERRIDE`, `FLAG_NOT_FOUND`, `CLIENT_NOT_READY`).

## Testing (no network)

Use the `configure()` siblings — seed overrides, read through the same `Client`:

```python
shipeasy.configure_for_testing(
    flags={"new_checkout": True},
    configs={"billing_copy": {"title": "Welcome"}},
    experiments={"checkout_button": ("treatment", {"color": "green"})},
)
assert shipeasy.Client({"user_id": "u_123"}).get_flag("new_checkout") is True
```

Offline (real rules from a snapshot / file):

```python
shipeasy.configure_for_offline(path="snapshot.json")
# or snapshot={"flags": {...}, "experiments": {...}}, plus optional overrides
```

## OpenFeature

```python
import shipeasy                                   # pip install "shipeasy[openfeature]"
from openfeature import api
from shipeasy.openfeature import ShipeasyProvider

shipeasy.configure(api_key="sdk_server_...", poll=True)
api.set_provider(ShipeasyProvider())             # uses the configured global
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
- `configure(private_attributes=[...])` strips keys from outbound events.
- `configure(sticky_store=InMemoryStickyStore())` pins experiment assignment.
- `client.log_exposure(exp_name)` for manual exposure.
- SSR: `shipeasy.bootstrap_script_tag(user)` + `shipeasy.i18n_script_tag(client_key, "en:prod")`.

## i18n

No server-side `t()`. The browser's Shipeasy **client** SDK renders labels; this
server SDK only emits the loader tag (public client key) during SSR.
