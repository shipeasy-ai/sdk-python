# A/B experiments — `universe(name).assign()` + `track`

After [`configure()`](configuration.md), an experiment is **end-to-end through
the bound `shipeasy.Client(user)`** — read the assignment (the first `get()`
logs exposure) and track the conversion, all on the same handle, with no user
argument.

## Universes, not experiment names

A **universe is a mutual-exclusion pool**: a unit is enrolled in **at most one**
experiment in it. You no longer read an experiment by name — you ask a universe
for an assignment:

```python
# construct once per callsite (cheap; binds the user)
client = shipeasy.Client(current_user)

a = client.universe("checkout").assign()
if a.get("button_color") == "green":
    ...
```

`universe(name)` returns a reusable handle; `assign()` picks the ≤1 experiment the
bound unit is pooled into within the universe and returns an `Assignment`.

## The `Assignment` handle

`assign()` never throws. The returned `Assignment` exposes:

- `.name` (`str | None`) — the experiment the unit landed in, or `None` when not
  enrolled.
- `.group` (`str | None`) — the assigned variation group, or `None` when not
  enrolled.
- `.enrolled` (`bool`) — `True` iff enrolled (`group is not None`).
- `.get(field, fallback=None, *, exposure=True)` — the resolved param: the
  assigned variant's override, else the **universe default**, else `fallback`. It
  works even when the unit is not enrolled — you get `universe default → fallback`
  — because the universe owns the param schema and its defaults. The **first**
  `get()` on an enrolled assignment logs the exposure (see below); pass
  `exposure=False` to peek at a param without logging one.

```python
a = client.universe("checkout").assign()
a.name        # "checkout_button" or None
a.group       # "treatment" or None
a.enrolled    # True / False
a.get("button_color", "red")   # variant override → universe default → "red"
```

## Exposure fires on read

Reading *is* the exposure. `assign()` itself is side-effect free — the exposure
is logged the **first time you read a param** via `get()` on an enrolled
assignment, i.e. at the point you actually present the treatment. It's deduped
per process *and* durably per `(unit, experiment, group)` server-side, so
repeated `get()` calls — and repeated `assign()` calls across requests — don't
spam the collector. There is no manual `log_exposure` primitive.

Pass `exposure=False` to **peek** at a param without logging anything:

```python
a = client.universe("checkout").assign()   # no exposure yet
color = a.get("button_color", "red", exposure=False)   # peek — still no exposure
if user_will_see_it:
    color = a.get("button_color", "red")   # first real read → logs one exposure
```

Exposure is a no-op under
[`configure_for_testing` / `configure_for_offline`](testing.md).

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
