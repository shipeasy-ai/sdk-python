# Error reporting — `see()`

The Python SDK ships the `see()` structured-error surface. It reports a **caught,
handled** error (or a non-exception "violation") to Shipeasy as a fire-and-forget
event — without re-raising. Reporting must never raise into your code.

## Reporting a handled exception

`see(problem)` returns a chainable builder. The terminal is `.to(outcome)` — it
builds the event and fires it:

```python
from shipeasy import see

try:
    charge(order)
except PaymentError as e:
    see(e).causes_the("checkout").to("use the backup processor")
    fallback_charge(order)
```

`.causes_the(subject)` and `.extras(mapping)` are chainable setters callable in
any order **before** `.to`. You can also fold the extras into the terminal as
`.to(outcome, extras)`, so there is no ordering to remember:

```python
see(e).causes_the("checkout").extras({"order_id": oid}).to("use cached prices")

# equivalent, extras inline on the terminal:
see(e).causes_the("checkout").to("use cached prices", {"order_id": oid})
```

A stray `.extras` chained **after** `.to` is ignored with a warning (the report
already shipped) — it never raises into your `except` block (`.to` returns the
chain).

Use the package-level `see()` — it reports against the engine you set up with
[`configure()`](configuration.md). No object to construct or pass around.

### Attach context from anywhere: `add_extras`

To attach context without threading it into the `except` block, buffer it earlier
in the request with `shipeasy.add_extras`. Every `see()` report that fires later
in the **same request** merges it in:

```python
import shipeasy

# from any layer, early in the request (mapping and/or keyword args)
shipeasy.add_extras(order_id=order.id, tenant=tenant.slug)

# ...later, deep in a service...
try:
    charge(order)
except PaymentError as e:
    shipeasy.see(e).causes_the("checkout").to("use cached prices")
    # report carries order_id + tenant automatically
```

The buffer is backed by a **`ContextVar`**, so concurrent requests and async
tasks never bleed into each other, and it merges into *every* report in the
request (not just the first). A chained `.extras` / `.to` extra of the same key
overrides an ambient one. The WSGI / ASGI / Django middleware clears the buffer
at the end of each request; in a background job or script call
`shipeasy.clear_extras()` when a unit of work ends.

## Non-exception violations

```python
from shipeasy import see_violation, Violation

see_violation("missing_invoice").causes_the("billing").to("skip the dunning email")
```

## Control-flow exceptions (report NOTHING)

`control_flow_exception(e).because("...")` marks an exception **expected** and
transmits nothing — `.extras()` is stored for local debugging only:

```python
from shipeasy import control_flow_exception

try:
    parse(token)
except StopIteration as e:
    control_flow_exception(e).because("end of stream is expected")
```

## Spam guard

The SDK carries a per-process limiter, so repeated reports of the same issue
collapse to a single send.
