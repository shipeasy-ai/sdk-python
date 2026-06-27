# Feature flags — `get_flag`

A flag (gate) evaluates to a boolean for a given user.

## Bound `Client(user)` form

```python
client = shipeasy.Client(current_user)
if client.get_flag("new_checkout"):
    ...
```

## Low-level `Engine` form

The engine takes the user on each call:

```python
if engine.get_flag("new_checkout", {"user_id": "u_123", "country": "US"}):
    ...
```

## Default / fallback behaviour

`get_flag` takes a `default` that is returned **only when the value cannot be
evaluated** — never when the gate simply resolves off:

```python
# default is returned only if the engine isn't initialized OR the gate isn't
# in the blob. A gate that evaluates to False returns False, NOT the default.
engine.get_flag("new_checkout", {"user_id": "u_123"}, default=True)

# Bound form:
shipeasy.Client(user).get_flag("new_checkout", default=True)
```

## Evaluation detail — `get_flag_detail`

`get_flag_detail` returns `FlagDetail(value, reason)` so you can log *why* a flag
resolved the way it did. `reason` is one of the exported constants:

```python
from shipeasy import (
    FlagDetail, CLIENT_NOT_READY, FLAG_NOT_FOUND, OFF, OVERRIDE, RULE_MATCH, DEFAULT,
)

d = engine.get_flag_detail("new_checkout", {"user_id": "u_123"})
# Bound: d = shipeasy.Client(user).get_flag_detail("new_checkout")
print(d.value, d.reason)   # e.g. True RULE_MATCH
```

| reason | meaning |
| --- | --- |
| `OVERRIDE` | a local `override_flag` forced the value (no telemetry) |
| `CLIENT_NOT_READY` | `init()`/`init_once()` hasn't run yet → `value=False` |
| `FLAG_NOT_FOUND` | no gate by that name in the blob → `value=False` |
| `OFF` | the gate exists but is disabled → `value=False` |
| `RULE_MATCH` | evaluated **on** (targeting + rollout) |
| `DEFAULT` | evaluated **off** (fell through) |

`get_flag` delegates to `get_flag_detail` and returns `.value`, substituting
`default` for the `CLIENT_NOT_READY` / `FLAG_NOT_FOUND` cases.

## Change listeners

Register a callback fired after a background poll fetches **new** data (a 200,
not a 304). It returns an unsubscribe callable; listeners never fire in
test/offline mode.

```python
unsubscribe = engine.on_change(lambda: print("flags changed, rebuild cache"))
...
unsubscribe()  # stop listening
```
