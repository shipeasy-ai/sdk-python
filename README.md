# shipeasy (Python)

Server SDK for [Shipeasy](https://shipeasy.dev) — feature flags, remote configs, A/B experiments, and metric tracking. Server-key only, never embed in browsers.

```bash
pip install shipeasy
```

```python
from shipeasy import Client

client = Client(api_key="sdk_server_...")
client.init()  # background poll; use init_once() for serverless

if client.get_flag("new_checkout", {"user_id": "u_123", "country": "US"}):
    ...

config = client.get_config("billing_copy")

result = client.get_experiment(
    "checkout_button",
    user={"user_id": "u_123"},
    default_params={"color": "blue"},
)
print(result.in_experiment, result.group, result.params)

client.track("u_123", "purchase", {"amount": 49})
```

## Anonymous visitors (zero-config bucketing)

For logged-out traffic you need a *stable* unit so a fractional rollout buckets
the same on the server and in the browser. The middleware mints a first-party
`__se_anon_id` cookie (shared with every Shipeasy SDK) for any request without
one; evaluations then **default to it** as `anonymous_id`, so `get_flag` on an
anonymous request just works — no per-call wiring.

```python
# WSGI (Flask, Django, ...)
from shipeasy.middleware import AnonIdMiddleware
app.wsgi_app = AnonIdMiddleware(app.wsgi_app)

# ASGI (FastAPI, Starlette)
from shipeasy.middleware import AnonIdASGIMiddleware
app.add_middleware(AnonIdASGIMiddleware)
```

```python
# logged-out request → buckets on the __se_anon_id cookie automatically
client.get_flag("new_checkout", {})
```

An explicit `user_id`/`anonymous_id` always wins. The id is also on the request
(`environ["shipeasy.anon_id"]`). The cookie is non-`HttpOnly` by design so the
browser SDK buckets identically; a request with **no** unit still resolves a
fully-rolled (100%) gate as on. Cookie name + format are a cross-SDK contract —
see `18-identity-bucketing.md`.

## Evaluation

Tested against the cross-language MurmurHash3 vectors in `experiment-platform/04-evaluation.md`.
