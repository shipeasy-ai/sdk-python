# A/B experiments — `get_experiment` + `track`

After [`configure()`](configuration.md), an experiment is **end-to-end through
the bound `shipeasy.Client(user)`** — read the assignment, log exposure, and
track the conversion, all on the same handle, with no user argument.

## Reading an experiment

`get_experiment` returns an `ExperimentResult` with three fields:

- `in_experiment` (`bool`) — is the user enrolled?
- `group` (`str | None`) — the assigned variation group.
- `params` (`dict`) — the variation parameters (falls back to `default_params`
  when the user isn't enrolled or no params are set).

```python
# construct once per callsite (cheap; binds the user)
client = shipeasy.Client(current_user)

result = client.get_experiment("checkout_button", default_params={"color": "blue"})
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
result = client.get_experiment("checkout_button", default_params={"color": "blue"})
client.log_exposure("checkout_button")   # at the decision point
```

It re-evaluates and, if the bound user is enrolled, POSTs a single `exposure`
event; otherwise it's a no-op (also a no-op under
[`configure_for_testing` / `configure_for_offline`](testing.md)).

## Tracking conversion events — `track`

Record a conversion/metric event for the experiment's success metric on the same
bound `Client`, deriving the unit from the bound attributes (`user_id` else
`anonymous_id`):

```python
client.track("{{SUCCESS_EVENT}}", {"amount": 49})
```

- `event_name` — your success-metric event, e.g. `{{SUCCESS_EVENT}}`.
- `properties` — optional event payload (any [private attributes](advanced.md)
  you configured are stripped before the event leaves the process).

`track()` is fire-and-forget and a no-op in test/offline mode. If the bound
attributes carry no `user_id` or `anonymous_id`, the call is a no-op.
