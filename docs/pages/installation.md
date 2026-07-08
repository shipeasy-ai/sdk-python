# Installation & configuration

This is the canonical home for **install + `configure()`**. Snippets elsewhere
assume `configure()` already ran at startup; this page is where it lives.

This is a **server** SDK: it authenticates with your **server key**
(`sdk_server_...`) and must never be embedded in a browser.

Requires **Python 3.8+**. The base package has no required third-party
dependencies (only the standard library).

## Install

```bash
# pip
pip install shipeasy

# poetry
poetry add shipeasy

# uv
uv add shipeasy
```

Import the package:

```python
import shipeasy
# or pull specific symbols:
from shipeasy import Client, configure, configure_for_testing
```

### Optional extras

The OpenFeature provider needs the `openfeature-sdk` package, shipped as an
optional extra. Install it only if you use `shipeasy.openfeature`:

```bash
pip install "shipeasy[openfeature]"      # poetry add "shipeasy[openfeature]" / uv add "shipeasy[openfeature]"
```

Importing the base `shipeasy` package never requires `openfeature-sdk`; only
importing `shipeasy.openfeature` does. See [openfeature](openfeature.md).

## `configure()` — once per process

Call `configure()` **once** at process start, then construct a cheap, user-bound
`Client(user)` per request — every read takes **no user argument** because the
user is bound at construction.

```python
import shipeasy

shipeasy.configure(
    api_key="sdk_server_...",                       # server key — never a browser
    attributes=lambda u: {                          # YOUR user object → attribute map
        "user_id": u.id, "country": u.country, "plan": u.plan,
    },
    init=True,                                       # one-shot fetch (default); see below
    # plus any option below (poll, base_url, env, private_attributes, …)
)
```

- **`api_key`** *(required)* — your Shipeasy **server key** (`sdk_server_...`).
  Authenticates flags, configs, kill switches and experiments. Read it from the
  environment (`os.environ["SHIPEASY_SERVER_KEY"]`); never hard-code it.
- **`attributes`** *(optional)* — a transform from YOUR user object to the
  Shipeasy attribute map that targeting evaluates against. The default is
  identity, so if your user object is already that map you can omit it:

  ```python
  shipeasy.configure(api_key="sdk_server_...")
  # construct once per callsite (cheap; binds the user)
  client = shipeasy.Client({"user_id": "u_123", "country": "US"})
  client.get_flag("new_checkout")
  ```
- **`init`** *(optional, default `True`)* — fire a one-shot fetch (in a daemon
  thread) so the first `Client(user).get_flag(...)` resolves against real rules.
  Ideal for serverless / short-lived processes.
- **`poll`** *(optional, default `False`)* — for a long-running server, pass
  `poll=True` to start the **background poll** (initial fetch + periodic refresh)
  so flags stay fresh without a redeploy. Configuration owns the lifecycle:

  ```python
  shipeasy.configure(api_key="sdk_server_...", poll=True)
  ```

**`configure()` options.** Beyond `api_key`, `attributes`, `init` and `poll`,
`configure()` accepts the following advanced keywords:

| keyword | type | default | what it does |
| --- | --- | --- | --- |
| `base_url` | `str` | `https://api.shipeasy.ai` | API base URL for the flag/experiment blobs. Override for a self-hosted edge or in tests; a trailing slash is stripped. |
| `env` | `str` | `"prod"` | Deployment environment tag, attached to `see()` error events and usage telemetry so the dashboard can split by environment. |
| `disable_telemetry` | `bool` | `False` | Opt out of per-evaluation usage telemetry (the fire-and-forget beacon). Evaluation itself is unaffected. |
| `telemetry_url` | `str` | built-in | Override the telemetry endpoint. Rarely needed; pair with a self-hosted collector. |
| `private_attributes` | `Sequence[str]` | `[]` | Attribute keys stripped from every outbound event `properties` bag before it leaves the process (LaunchDarkly/Statsig `privateAttributes`). They still drive **targeting** locally — they just never reach `/collect`. See [advanced](advanced.md). |
| `sticky_store` | `StickyBucketStore` | `None` | Pluggable store that pins a user's experiment group across re-buckets (doc 20 §2). Absent ⇒ purely deterministic hashing. See [advanced](advanced.md). |

```python
import shipeasy

# example: self-hosted edge, staging env, telemetry off, redact `email`
shipeasy.configure(
    api_key="sdk_server_...",
    base_url="https://flags.internal.acme.com",
    env="staging",
    disable_telemetry=True,
    private_attributes=["email", "ip"],
)
```

**Identity default.** The attribute map you produce is the unit of identity —
supply `user_id` for logged-in users, or let the anon-id middleware (below)
inject `anonymous_id` for logged-out traffic. An explicit
`user_id`/`anonymous_id` always wins. Constructing `Client(user)` before
`configure()` raises `RuntimeError`.

---

## Frameworks

`configure()` is the same everywhere — only **where you call it** and **how you
wire the anon-id middleware** differ. The middleware mints a first-party
`__se_anon_id` cookie (shared with every Shipeasy SDK) for any request without
one, so a fractional rollout buckets identically on the server and in the
browser; evaluations then default to it as `anonymous_id`.

### Django

Shipeasy ships a Django app (`shipeasy.django`) that calls `configure()` for you
from a `SHIPEASY` settings dict — the settings-driven, "configure once at boot"
equivalent of a Rails railtie. The fastest path:

```bash
pip install shipeasy
```

1. Add the app to `INSTALLED_APPS`:

   ```python
   # settings.py
   INSTALLED_APPS = [
       # ...
       "shipeasy.django",
   ]
   ```

2. Run the installer — it idempotently adds the anon-id middleware to
   `MIDDLEWARE`, appends a `SHIPEASY = {...}` config block to your settings, and
   (if a `.env` exists) appends `SHIPEASY_SERVER_KEY=`:

   ```bash
   python manage.py shipeasy_install
   ```

   It's safe to re-run (each edit is anchored + idempotent), and if it can't
   confidently edit a list it prints the exact lines to paste instead of
   corrupting the file. Flags: `--settings-file PATH` (override auto-detection
   from `DJANGO_SETTINGS_MODULE`), `--force`, `--no-env`.

3. Set your server key and (optionally) tune the config block:

   ```python
   # settings.py  (added by shipeasy_install)
   import os

   SHIPEASY = {
       # Required — your Shipeasy SERVER key (sdk_server_...); never a browser.
       "SERVER_KEY": os.environ.get("SHIPEASY_SERVER_KEY"),
       # Network egress — master switch for ALL outbound requests. Pinned to
       # Django's production convention (DEBUG is False in prod) so the SDK stays
       # quiet in dev/CI. Omit it to let the SDK infer prod from the environment.
       "NETWORK_ENABLED": not DEBUG,
       # Optional — map YOUR user object to the Shipeasy attribute map. A dotted
       # import path to a callable, OR a callable.
       "ATTRIBUTES": "myapp.shipeasy.user_attributes",
       # Optional engine knobs: "ENV", "DISABLE_TELEMETRY",
       # "PRIVATE_ATTRIBUTES", "BASE_URL".
       # Long-running server? set "POLL": True to keep flags fresh in the
       # background. Default False (serverless / short-lived).
       "POLL": False,
   }
   ```

   The `shipeasy.django` AppConfig reads this dict in `ready()` and calls
   `configure()` once at boot. If `SERVER_KEY` is missing it warns and no-ops
   (reads then raise until you set it). The `MIDDLEWARE` entry
   (`"shipeasy.django.middleware.AnonIdMiddleware"`) mints the shared
   `__se_anon_id` cookie for logged-out traffic and exposes it as
   `request.shipeasy_anon_id`.

Then read flags anywhere, per request:

```python
# views.py — bind the request user once, then read
import shipeasy


def checkout(request):
    # construct once per request (cheap; binds the user)
    client = shipeasy.Client(request.user)
    if client.get_flag("new_checkout"):
        ...
```

#### Manual wiring (no app / no installer)

Prefer not to use the `shipeasy.django` app? Call `configure()` yourself in any
`AppConfig.ready()` and wrap your WSGI app with the framework-agnostic
middleware:

```python
# myapp/apps.py
import os
from django.apps import AppConfig
import shipeasy


class MyAppConfig(AppConfig):
    name = "myapp"

    def ready(self) -> None:
        shipeasy.configure(
            api_key=os.environ["SHIPEASY_SERVER_KEY"],
            attributes=lambda u: {"user_id": str(u.id), "plan": u.plan},
        )
```

```python
# myproject/wsgi.py
import os
from django.core.wsgi import get_wsgi_application
from shipeasy.middleware import AnonIdMiddleware

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")

application = AnonIdMiddleware(get_wsgi_application())
```

On ASGI (`asgi.py`), wrap with `AnonIdASGIMiddleware` instead — see FastAPI.

### Flask (WSGI)

Configure at module import (or inside `create_app()`), and wrap `app.wsgi_app`
with `AnonIdMiddleware`.

```python
import os
import shipeasy
from shipeasy.middleware import AnonIdMiddleware
from flask import Flask

shipeasy.configure(
    api_key=os.environ["SHIPEASY_SERVER_KEY"],
    attributes=lambda u: {"user_id": u.id, "plan": u.plan},
)

app = Flask(__name__)
app.wsgi_app = AnonIdMiddleware(app.wsgi_app)


@app.get("/checkout")
def checkout():
    # construct once per request (cheap; binds the user)
    client = shipeasy.Client(current_user)
    if client.get_flag("new_checkout"):
        ...
```

### FastAPI / Starlette (ASGI)

Configure in a startup hook (or at import), and add `AnonIdASGIMiddleware` via
`app.add_middleware`.

```python
import os
import shipeasy
from shipeasy.middleware import AnonIdASGIMiddleware
from fastapi import FastAPI, Request

app = FastAPI()
app.add_middleware(AnonIdASGIMiddleware)


@app.on_event("startup")
def _configure() -> None:
    shipeasy.configure(
        api_key=os.environ["SHIPEASY_SERVER_KEY"],
        attributes=lambda u: {"user_id": u.id, "plan": u.plan},
    )


@app.get("/checkout")
def checkout(request: Request):
    # construct once per request (cheap; binds the user)
    client = shipeasy.Client(current_user(request))
    if client.get_flag("new_checkout"):
        ...
```

A logged-out request (`shipeasy.Client({})`) buckets on the `__se_anon_id`
cookie automatically; the id is also on the request
(`environ["shipeasy.anon_id"]` for WSGI). Cookie name + format are a cross-SDK
contract — see `18-identity-bucketing.md`.

## Tests and offline

For unit tests and offline evaluation, swap `configure()` for one of its drop-in
siblings — no api key, no network — then read through the same
`shipeasy.Client(user)`:

```python
# unit tests: seed values, zero network
shipeasy.configure_for_testing(flags={"new_checkout": True})

# offline: evaluate the real rules from a snapshot / file
shipeasy.configure_for_offline(path="shipeasy-snapshot.json")
```

See [testing](testing.md) for the full override args.
