# shipeasy (Python)

Server SDK for [Shipeasy](https://shipeasy.dev) — feature flags, remote configs,
kill switches, A/B experiments, and metric tracking. Server-key only, never embed
in browsers.

> **Full documentation** lives in [`docs/`](docs/) and is published to
> **<https://shipeasy-ai.github.io/sdk-python/>**. GitHub can't inline those pages
> into this README, so the **Documentation** index below links each one.

## Install

```bash
pip install shipeasy      # poetry add shipeasy  ·  uv add shipeasy
```

Requires Python 3.8+. See [Installation](docs/pages/installation.md) for the
per-framework setup (Django / Flask / FastAPI) and the anon-id middleware.

## Configure once, then `Client(user)` per request

Two things only: `configure()` once at startup, then a cheap user-bound
`shipeasy.Client(user)` per request — every call takes **no user argument**
because the user is bound at construction.

```python
import shipeasy

# Once, at startup. `attributes` maps YOUR user object → the Shipeasy attribute
# map (omit it if your user object already is that map). poll=True keeps the blob
# fresh in the background for a long-running server.
shipeasy.configure(
    api_key="sdk_server_...",
    attributes=lambda u: {"user_id": u.id, "country": u.country, "plan": u.plan},
)

# Per request — construct once per callsite, then read with no user argument.
client = shipeasy.Client(current_user)

if client.get_flag("new_checkout"):
    ...
config = client.get_config("billing_copy")
result = client.get_experiment("checkout_button", default_params={"color": "blue"})
client.log_exposure("checkout_button")     # at the decision point
client.track("purchase", {"amount": 49})   # on conversion
```

Constructing `Client(user)` before `configure()` raises `RuntimeError`. See
[Configuration](docs/pages/configuration.md) for every option (`attributes`,
`init`/`poll`, `base_url`, `private_attributes`, `sticky_store`, …).

## Documentation

Each page is also served raw at `https://shipeasy-ai.github.io/sdk-python/pages/<name>.md`.

- [Overview](docs/pages/overview.md) — the `configure()` + `Client(user)` model
- [Installation](docs/pages/installation.md) — install, frameworks, `configure()` wiring
- [Configuration](docs/pages/configuration.md) — keys, `attributes`, one-shot vs poll, all options
- [Feature flags](docs/pages/flags.md) — `get_flag`, `get_flag_detail`, defaults
- [Dynamic configs](docs/pages/configs.md) — `get_config`, typed decode, defaults
- [Kill switches](docs/pages/killswitches.md) — `get_killswitch`, named switches
- [Experiments](docs/pages/experiments.md) — `get_experiment`, `log_exposure`, `track`
- [Internationalization (i18n)](docs/pages/i18n.md) — SSR loader tag (render is client-side)
- [Error reporting](docs/pages/error-reporting.md) — `see()` structured reporting
- [Testing](docs/pages/testing.md) — `configure_for_testing` / `configure_for_offline`, overrides
- [OpenFeature](docs/pages/openfeature.md) — `ShipeasyProvider`
- [Advanced](docs/pages/advanced.md) — anon-id middleware, private attrs, sticky bucketing, SSR

Copy-paste snippets live under [`docs/snippets/`](docs/snippets/) (release, metrics,
i18n, ops); an installable agent skill is at [`docs/skill/SKILL.md`](docs/skill/SKILL.md).

## Testing

Swap `configure()` for a drop-in sibling — no api key, no network — then read
through the same `shipeasy.Client(user)`:

```python
import shipeasy

# unit tests: seed values, zero network
shipeasy.configure_for_testing(
    flags={"new_checkout": True},
    configs={"billing_copy": {"title": "Welcome"}},
    experiments={"checkout_button": ("treatment", {"color": "green"})},
)
client = shipeasy.Client({"user_id": "u_123"})
assert client.get_flag("new_checkout") is True

# flip values on the spot, mid-test, without reconfiguring:
shipeasy.override_flag("new_checkout", False)
shipeasy.clear_overrides()

# offline: evaluate the REAL rules from a snapshot / file (overrides apply on top)
shipeasy.configure_for_offline(path="shipeasy-snapshot.json")
```

`configure_for_testing()` **replaces** any prior configuration so each test
reconfigures freely. Full details — the override helpers and a working example
`shipeasy-snapshot.json` — in [Testing](docs/pages/testing.md).

## Evaluation

Tested against the cross-language MurmurHash3 vectors in `experiment-platform/04-evaluation.md`.
