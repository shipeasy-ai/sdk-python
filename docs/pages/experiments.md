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

## Logging exposure — `log_exposure`

The server is stateless and never auto-logs exposure. Call `log_exposure` at the
point you actually present the treatment (parity with the browser's
auto-exposure). The bound `Client` derives the user from the same bound
attributes you read the experiment with — no user argument:

```python
client = shipeasy.Client(current_user)
result = client.get_experiment("checkout_button", default_params={"color": "blue"})
client.log_exposure("checkout_button")   # at the decision point
```

It re-evaluates and, if the bound user is enrolled, POSTs a single `exposure`
event; otherwise it's a no-op (also a no-op in test/offline mode).

## Tracking conversion events — `track`

Record a conversion/metric event for the experiment's success metric. The bound
`Client` is the primary path — the same handle you used for `get_experiment`
records the conversion, deriving the unit from the bound attributes
(`user_id` else `anonymous_id`):

```python
client.track("{{SUCCESS_EVENT}}", {"amount": 49})
```

- `event_name` — your success-metric event, e.g. `{{SUCCESS_EVENT}}`.
- `properties` — optional event payload (any [private attributes](advanced.md)
  configured on the engine are stripped before the event leaves the process).

`track()` is fire-and-forget and a no-op in test/offline mode. If the bound
attributes carry no `user_id` or `anonymous_id`, the call is a no-op.

### Low-level `Engine` form

For advanced use (outside a bound `Client`), `track`/`log_exposure` live on the
`Engine` and take the user explicitly:

```python
engine.track("u_123", "{{SUCCESS_EVENT}}", {"amount": 49})
engine.log_exposure({"user_id": "u_123"}, "checkout_button")
```
