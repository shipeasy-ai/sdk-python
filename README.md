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

Tested against the cross-language MurmurHash3 vectors in `experiment-platform/04-evaluation.md`.
