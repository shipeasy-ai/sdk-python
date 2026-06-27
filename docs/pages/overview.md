# Shipeasy Python SDK — Overview

`shipeasy` is the **server** SDK for Shipeasy — feature flags, remote configs,
kill switches, A/B experiments, and metric tracking. It uses your **server key**
and must never be embedded in a browser.

## Mental model: `configure()` once, then `Client(user)` per request

Configure the SDK **once** at process start with your server key and an optional
`attributes` transform (your user object → the Shipeasy attribute map). Then
construct a cheap, **user-bound** `Client(user)` per request — every call takes
**no user argument** because the user is bound at construction.

```python
import shipeasy

shipeasy.configure(
    api_key="sdk_server_...",
    attributes=lambda u: {"user_id": u.id, "country": u.country, "plan": u.plan},
)

client = shipeasy.Client(current_user)
if client.get_flag("new_checkout"):
    ...
config = client.get_config("billing_copy")
result = client.get_experiment("checkout_button", default_params={"color": "blue"})
```

## Engine vs Client

- **`Engine`** is the heavyweight object: it owns the cached blob, the background
  poll, `track()`, `see()`, the `override_*` setters, and the offline factories
  (`for_testing` / `from_file` / `from_snapshot`). It takes the user on **each**
  call.
- **`Client(user)`** is a thin, per-request handle over the shared engine built
  by `configure()`. The user is bound once; calls omit it. Constructing a
  `Client(user)` before `configure()` raises `RuntimeError`.

`configure()` builds one shared engine (first-config-wins) and kicks off a
one-shot fetch, so the first `Client(user).get_flag(...)` resolves against real
rules.

## Feature pages

- [installation](installation.md) — `pip install shipeasy`, runtime, import line
- [configuration](configuration.md) — `configure()`, keys, `attributes`, init/poll
- [flags](flags.md) — `get_flag`, `get_flag_detail`, defaults
- [configs](configs.md) — `get_config`, typed decode, defaults
- [killswitches](killswitches.md) — `get_killswitch`
- [experiments](experiments.md) — `get_experiment`, `ExperimentResult`, `track`
- [i18n](i18n.md) — cross-SDK loader story (server SDK has no `t()`)
- [error-reporting](error-reporting.md) — `see()` structured reporting
- [testing](testing.md) — `for_testing`, `from_file`, `override_*`
- [openfeature](openfeature.md) — `ShipeasyProvider`
- [advanced](advanced.md) — anon-id middleware, private attrs, sticky bucketing, manual exposure, SSR
