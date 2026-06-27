# Testing

Use `Engine.for_testing()` in unit tests: it does **zero network**, needs no
api_key, disables telemetry, and makes `init()`/`init_once()`/`track()` no-ops.
Seed every entity with the `override_*` setters (Statsig-style local overrides) —
an override always wins over whatever the engine would otherwise resolve.

```python
from shipeasy import Engine

engine = Engine.for_testing()  # no key, no network, immediately usable

# Flags
engine.override_flag("new_checkout", True)
assert engine.get_flag("new_checkout", {"user_id": "u_123"}) is True

# Configs (decode is optional and still applies)
engine.override_config("billing_copy", {"title": "Welcome"})
assert engine.get_config("billing_copy") == {"title": "Welcome"}
assert engine.get_config("billing_copy", decode=lambda v: v["title"]) == "Welcome"

# Experiments → ExperimentResult(in_experiment=True, group=..., params=...)
engine.override_experiment("checkout_button", group="treatment", params={"color": "green"})
result = engine.get_experiment(
    "checkout_button",
    user={"user_id": "u_123"},
    default_params={"color": "blue"},
)
assert result.in_experiment and result.group == "treatment"
assert result.params == {"color": "green"}

# track() is a no-op in test mode — safe to call, sends nothing
engine.track("u_123", "purchase", {"amount": 49})

# Reset between cases
engine.clear_overrides()
```

The same `override_*` / `clear_overrides()` setters work on a normal `Engine`
too, if you want to pin a value in a live engine.

## Offline snapshot

Run fully offline against a JSON snapshot — evaluations run the **real** eval
logic, no network is touched, and `override_*` still applies on top:

```python
# From a file: {"flags": <body of /sdk/flags>, "experiments": <body of /sdk/experiments>}
engine = Engine.from_file("shipeasy-snapshot.json")

# Or from in-memory blobs
engine = Engine.from_snapshot(
    flags={"gates": {...}, "configs": {...}},
    experiments={"experiments": {...}, "universes": {...}},
)

engine.get_flag("new_checkout", {"user_id": "u_123"})
```
