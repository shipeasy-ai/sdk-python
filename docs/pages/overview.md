# Shipeasy Python SDK — Overview

`shipeasy` is the **server** SDK for Shipeasy — feature flags, remote configs,
kill switches, A/B experiments, and metric tracking. It uses your **server key**
and must never be embedded in a browser.

## Mental model: `configure()` once, then `Client(user)` per request

There are exactly two things to learn:

1. **`configure()`** — call it **once** at process start with your server key and
   an optional `attributes` transform (your user object → the Shipeasy attribute
   map). This is the whole setup story.
2. **`shipeasy.Client(user)`** — construct a cheap, **user-bound** handle per
   request and read with **no user argument** (the user is bound at construction).

```python
import shipeasy

shipeasy.configure(
    api_key="sdk_server_...",
    attributes=lambda u: {"user_id": u.id, "country": u.country, "plan": u.plan},
)

# construct once per callsite (cheap; binds the user)
client = shipeasy.Client(current_user)

if client.get_flag("new_checkout"):
    ...
config = client.get_config("billing_copy")
a = client.universe("checkout").assign()  # ≤1 experiment; auto-logs exposure
if a.get("button_color") == "green":
    ...
client.track("purchase", {"amount": 49})  # on conversion
```

## What the bound `Client` does

Everything you need per request is on `Client(user)` — no user argument on any
call:

- `get_flag(name, default=False)` · `get_flag_detail(name)`
- `get_config(name, decode=None, default=None)`
- `get_killswitch(name, switch_key=None)`
- `universe(name).assign()` → `Assignment` (`.name` / `.group` / `.enrolled` /
  `.get(field, fallback=None)`); auto-logs one exposure when enrolled
- `track(event, properties=None)`

So an experiment is **end-to-end Client-only**. Constructing a `Client(user)`
before `configure()` raises `RuntimeError`.

## The configure family

| call | when |
| --- | --- |
| [`configure(api_key=...)`](configuration.md) | production — your server key |
| [`configure_for_testing(...)`](testing.md) | unit tests — no network, seed overrides |
| [`configure_for_offline(...)`](testing.md) | evaluate real rules from a snapshot / file |

After any of them, you read the same way: `shipeasy.Client(user)`.

## Feature pages

- [installation](installation.md) — `pip install shipeasy`, frameworks, `configure()`
- [configuration](configuration.md) — `configure()`, keys, `attributes`, one-shot vs poll, options
- [flags](flags.md) — `get_flag`, `get_flag_detail`, defaults
- [configs](configs.md) — `get_config`, typed decode, defaults
- [killswitches](killswitches.md) — `get_killswitch`
- [experiments](experiments.md) — `universe(name).assign()`, `Assignment`, auto-exposure, `track`
- [i18n](i18n.md) — cross-SDK loader story (server SDK has no `t()`)
- [error-reporting](error-reporting.md) — `see()` structured reporting
- [testing](testing.md) — `configure_for_testing`, `configure_for_offline`, overrides
- [openfeature](openfeature.md) — `ShipeasyProvider`
- [advanced](advanced.md) — anon-id middleware, private attrs, sticky bucketing, manual exposure, SSR
