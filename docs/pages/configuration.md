# Configuration

## `configure(...)` — the once-per-process call

```python
import shipeasy

shipeasy.configure(
    api_key="sdk_server_...",
    attributes=lambda u: {"user_id": u.id, "country": u.country, "plan": u.plan},
)
```

- **`api_key`** — your Shipeasy **server key** (`sdk_server_...`). Authenticates
  flags, configs, kill switches and experiments. Never embed it in a browser.
- **`attributes`** — a transform from YOUR user object to the Shipeasy attribute
  map that targeting evaluates against. The default is identity, so if your user
  object is already that map you can omit it:

  ```python
  shipeasy.configure(api_key="sdk_server_...")
  shipeasy.Client({"user_id": "u_123", "country": "US"}).get_flag("new_checkout")
  ```

`configure()` returns the single shared `Engine` (first-config-wins) and kicks
off a one-shot fetch fire-and-forget, so the first
`Client(user).get_flag(...)` resolves against real rules.

## Identity default

The attribute map you produce is the **unit of identity** — supply `user_id`
for logged-in users, or let the [anon-id middleware](advanced.md) inject
`anonymous_id` for logged-out traffic. An explicit `user_id`/`anonymous_id`
always wins.

## One-shot vs background poll

For a long-running server that wants the background poll (instead of the
one-shot fetch), pass `init=False` and call `init()` on the returned engine:

```python
engine = shipeasy.configure(api_key="sdk_server_...", init=False)
engine.init()  # start the background poll thread
```

## Low-level: constructing an `Engine` directly

`Client(user)` is a thin handle over an `Engine`. You can also build and own the
engine yourself — it takes the user on each call:

```python
from shipeasy import Engine

engine = Engine(api_key="sdk_server_...")
engine.init()        # background poll; use init_once() for serverless/one-shot

engine.get_flag("new_checkout", {"user_id": "u_123", "country": "US"})
```

`Engine(...)` also accepts: `base_url`, `env` (deployment env tag, default
`"prod"`), `disable_telemetry`, `telemetry_url`,
`private_attributes` (see [advanced](advanced.md)), and `sticky_store`.

> **Breaking change in 0.8.0:** the heavyweight client class was renamed
> `Client` → `Engine`, and `Client` is now the lightweight user-bound handle.
> Replace `Client(api_key=...)` with `Engine(api_key=...)`, or adopt
> `configure()` + `Client(user)`.
