# OpenFeature provider

The Python SDK ships an **OpenFeature server provider**,
`shipeasy.openfeature.ShipeasyProvider`, so apps standardised on the CNCF
OpenFeature API can plug Shipeasy in as the backing provider. It is a pure
adapter over the engine you set up with `shipeasy.configure(...)` — evaluation is
unchanged and runs locally against the cached blob (effectively synchronous).

## Install the extra

The provider needs the optional `openfeature-sdk` dependency:

```bash
pip install "shipeasy[openfeature]"
```

Importing the base `shipeasy` package never requires `openfeature-sdk`; only
importing `shipeasy.openfeature` does.

## Wiring

```python
import shipeasy
from openfeature import api
from openfeature.evaluation_context import EvaluationContext
from shipeasy.openfeature import ShipeasyProvider

shipeasy.configure(api_key="sdk_server_...", poll=True)
api.set_provider(ShipeasyProvider())  # uses the configured global engine

of = api.get_client()
on = of.get_boolean_value("new_checkout", False, EvaluationContext("u1"))
```

(`ShipeasyProvider()` resolves automatically from `configure()` — construct it
after your `configure(...)` call.)

The `EvaluationContext` `targeting_key` becomes `user_id`; every attribute is
carried through verbatim for targeting.

## Type routing

- **boolean** → evaluates the **gate** via `get_flag_detail`.
- **string / integer / float / object** → routes to **`get_config`**.

## Reason mapping (Shipeasy → OpenFeature)

| Shipeasy reason | OpenFeature reason | error code |
| --- | --- | --- |
| `RULE_MATCH` | `TARGETING_MATCH` | — |
| `DEFAULT` | `DEFAULT` | — |
| `OFF` | `DISABLED` | — |
| `OVERRIDE` | `STATIC` | — |
| `FLAG_NOT_FOUND` | `ERROR` | `FLAG_NOT_FOUND` |
| `CLIENT_NOT_READY` | `ERROR` | `PROVIDER_NOT_READY` |

A config that is absent resolves to the OpenFeature `default_value` with reason
`DEFAULT`; a present-but-wrong-type config returns the default with
`TYPE_MISMATCH`. Exceptions never propagate to OpenFeature — they surface as
reason `ERROR` / `GENERAL`.
