# Feature flags — `get_flag`

A flag (gate) evaluates to a boolean for a given user. After
[`configure()`](configuration.md) has run once at startup, bind a user with
`shipeasy.Client(user)` and read with **no user argument**.

```python
# construct once per callsite (cheap; binds the user)
client = shipeasy.Client(current_user)

if client.get_flag("new_checkout"):
    ...
```

## Default / fallback behaviour

`get_flag(name, default=False)` returns `default` **only when the value cannot be
evaluated** — never when the gate simply resolves off:

```python
# default is returned only if Shipeasy isn't ready yet OR the gate isn't in the
# blob. A gate that evaluates to False returns False, NOT the default.
client.get_flag("new_checkout", default=True)
```

## Evaluation detail — `get_flag_detail`

`get_flag_detail` returns `FlagDetail(value, reason)` so you can log *why* a flag
resolved the way it did. `reason` is one of the exported constants:

```python
from shipeasy import (
    FlagDetail, CLIENT_NOT_READY, FLAG_NOT_FOUND, OFF, OVERRIDE, RULE_MATCH, DEFAULT,
)

d = client.get_flag_detail("new_checkout")
print(d.value, d.reason)   # e.g. True RULE_MATCH
```

| reason | meaning |
| --- | --- |
| `OVERRIDE` | a [`configure_for_testing`](testing.md) override forced the value |
| `CLIENT_NOT_READY` | the first fetch hasn't completed yet → `value=False` |
| `FLAG_NOT_FOUND` | no gate by that name in the blob → `value=False` |
| `OFF` | the gate exists but is disabled → `value=False` |
| `RULE_MATCH` | evaluated **on** (targeting + rollout) |
| `DEFAULT` | evaluated **off** (fell through) |

`get_flag` delegates to `get_flag_detail` and returns `.value`, substituting
`default` for the `CLIENT_NOT_READY` / `FLAG_NOT_FOUND` cases.

## Change listeners

When you run a long-lived server with `configure(poll=True)`, register a callback
fired after a background poll fetches **new** data (a 200, not a 304). It returns
an unsubscribe callable:

```python
import shipeasy

unsubscribe = shipeasy.on_change(lambda: print("flags changed, rebuild cache"))
...
unsubscribe()  # stop listening
```
