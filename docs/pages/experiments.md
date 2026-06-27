# A/B experiments — `get_experiment` + `track`

## Reading an experiment

`get_experiment` returns an `ExperimentResult` with three fields:

- `in_experiment` (`bool`) — is the user enrolled?
- `group` (`str | None`) — the assigned variation group.
- `params` (`dict`) — the variation parameters (falls back to `default_params`
  when the user isn't enrolled or no params are set).

### Bound `Client(user)` form

```python
client = shipeasy.Client(current_user)
result = client.get_experiment("checkout_button", default_params={"color": "blue"})
print(result.in_experiment, result.group, result.params)
```

### Low-level `Engine` form

The engine takes the `user` keyword on each call:

```python
result = engine.get_experiment(
    "checkout_button",
    user={"user_id": "u_123"},
    default_params={"color": "blue"},
)
print(result.in_experiment, result.group, result.params)
```

Pass `decode=` to project `params` into a typed shape (applied only when the
user is enrolled; failures fall back to `default_params`).

## Tracking conversion events — `track`

Record a conversion/metric event for the experiment's success metric. `track`
lives on the `Engine` and takes the user id explicitly:

```python
engine.track("u_123", "{{SUCCESS_EVENT}}", {"amount": 49})
```

- `user_id` — the unit the event is attributed to.
- `event_name` — your success-metric event, e.g. `{{SUCCESS_EVENT}}`.
- `properties` — optional event payload (any [private attributes](advanced.md)
  configured on the engine are stripped before the event leaves the process).

`track()` is fire-and-forget and a no-op in test/offline mode.
