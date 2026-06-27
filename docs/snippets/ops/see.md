Report a caught, handled error (or a non-exception "violation") to Shipeasy with
`see()` — fire-and-forget, never re-raises. Package-level, so it reports against
the engine from `configure()`. Assumes `configure()` ran at startup — see
Installation.

### Report a handled exception

```python
from shipeasy import see

try:
    charge(order)
except PaymentError as e:
    # .causes_the(subject)        what the error affects (e.g. "checkout")
    # .to(outcome)                the terminal — what you do about it; builds + fires
    see(e).causes_the("checkout").to("use the backup processor")
    fallback_charge(order)
```

### Attach context with `.extras(...)`

```python
from shipeasy import see

try:
    charge(order)
except PaymentError as e:
    # .extras(mapping)            structured fields attached to the report
    see(e).causes_the("checkout").extras({"order_id": oid}).to("use cached prices")
```

### Report a non-exception violation

```python
from shipeasy import see_violation

# a bad state that isn't an exception — same chain, .to() is the terminal
see_violation("missing_invoice").causes_the("billing").to("skip the dunning email")
```

### Mark an expected exception — report NOTHING

```python
from shipeasy import control_flow_exception

try:
    parse(token)
except StopIteration as e:
    # transmits nothing; .because(...) / .extras() are local-debug only
    control_flow_exception(e).because("end of stream is expected")
```
