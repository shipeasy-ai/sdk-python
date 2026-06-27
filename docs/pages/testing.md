# Testing

Use **`configure_for_testing()`** — the test-mode sibling of
[`configure()`](configuration.md). It does **zero network**, needs no api_key,
and seeds the values your code under test should see via override arguments. Then
read through the ordinary `shipeasy.Client(user)` — the *same* call your
production code uses.

```python
import shipeasy
from shipeasy import Client

shipeasy.configure_for_testing(
    flags={"new_checkout": True},
    configs={"billing_copy": {"title": "Welcome"}},
    experiments={"checkout_button": ("treatment", {"color": "green"})},
)

# construct once per callsite (cheap; binds the user)
client = Client({"user_id": "u_123"})

assert client.get_flag("new_checkout") is True
assert client.get_config("billing_copy") == {"title": "Welcome"}

result = client.get_experiment("checkout_button", default_params={"color": "blue"})
assert result.in_experiment and result.group == "treatment"
assert result.params == {"color": "green"}

# track()/log_exposure() are no-ops in test mode — safe to call, send nothing
client.track("purchase", {"amount": 49})
```

Override argument shapes:

- `flags` — `{name: bool}` forced `get_flag` results.
- `configs` — `{name: value}` forced `get_config` results (a `decode` still applies).
- `experiments` — `{name: (group, params)}` forced enrolments.

`configure_for_testing()` **replaces** any previously-configured engine, so each
test can reconfigure freely (no reset boilerplate, unlike `configure()`'s
first-config-wins).

## Offline snapshot

Use **`configure_for_offline()`** to run fully offline against a real blob —
evaluations run the **real** eval logic (targeting, rollout, bucketing), no
network is touched, and the override args still apply on top:

```python
import shipeasy

# From a file: {"flags": <body of /sdk/flags>, "experiments": <body of /sdk/experiments>}
shipeasy.configure_for_offline(path="shipeasy-snapshot.json")

# …or from in-memory blobs, with optional overrides layered on top:
shipeasy.configure_for_offline(
    snapshot={
        "flags": {"gates": {...}, "configs": {...}},
        "experiments": {"experiments": {...}, "universes": {...}},
    },
    flags={"new_checkout": True},
)

client = shipeasy.Client({"user_id": "u_123"})
client.get_flag("new_checkout")
```

Both helpers take the same `attributes` transform as `configure()`, so your
user-object mapping is exercised in tests exactly as in production.
