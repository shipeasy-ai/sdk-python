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
from shipeasy import Engine, Client, configure
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
    # any Engine option as a keyword: base_url=, env="prod",
    # disable_telemetry=, private_attributes=[...], sticky_store=
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
  For a long-running server that wants the **background poll** instead, pass
  `init=False` and call `init()` on the returned engine:

  ```python
  engine = shipeasy.configure(api_key="sdk_server_...", init=False)
  engine.init()  # start the background poll thread
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

Configure once in `AppConfig.ready()`, and add the WSGI middleware to your
WSGI app (Django serves over WSGI by default).

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

```python
# views.py — bind the request user once, then read
import shipeasy


def checkout(request):
    # construct once per request (cheap; binds the user)
    client = shipeasy.Client(request.user)
    if client.get_flag("new_checkout"):
        ...
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

## Low-level: the `Engine` directly

`Client(user)` is a thin handle over a single shared `Engine`. You can build and
own the engine yourself — it takes the user on each call:

```python
from shipeasy import Engine

engine = Engine(api_key="sdk_server_...")
engine.init()        # background poll; use init_once() for serverless/one-shot

engine.get_flag("new_checkout", {"user_id": "u_123", "country": "US"})
```

`Engine(...)` also accepts: `base_url`, `env` (deployment env tag, default
`"prod"`), `disable_telemetry`, `telemetry_url`, `private_attributes`
(see [advanced](advanced.md)), and `sticky_store`.

> **Breaking change in 0.8.0:** the heavyweight client class was renamed
> `Client` → `Engine`, and `Client` is now the lightweight user-bound handle.
> Replace `Client(api_key=...)` with `Engine(api_key=...)`, or adopt
> `configure()` + `Client(user)`.
