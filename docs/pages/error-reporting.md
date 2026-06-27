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

`.causes_the(subject)` and `.extras(mapping)` are chainable setters; `.to(...)`
is the terminal:

```python
see(e).causes_the("checkout").extras({"order_id": oid}).to("use cached prices")
```

Use the package-level `see()` — it reports against the engine you set up with
[`configure()`](configuration.md). No object to construct or pass around.

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
