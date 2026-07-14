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
    # .extras(mapping)            structured fields attached to the report; call
    #                             it BEFORE .to, or pass extras inline as
    #                             .to(outcome, mapping). (A stray .extras AFTER
    #                             .to is ignored with a warning — it never raises
    #                             into the except block.)
    see(e).causes_the("checkout").extras({"order_id": oid}).to("use cached prices")

    # equivalent — extras folded into the terminal, no ordering to remember:
    see(e).causes_the("checkout").to("use cached prices", {"order_id": oid})
```

### Attach context from anywhere with `add_extras(...)`

```python
import shipeasy

# Buffer extras earlier in the request — from any layer, not just the except.
# Every see() report that fires LATER in the same request carries them, so you
# don't have to thread context down into the catch site. Backed by a ContextVar
# (concurrent requests / async tasks never mix); the WSGI/ASGI/Django middleware
# clears it per request (outside a request, call shipeasy.clear_extras yourself).
# Accepts a mapping and/or keyword args.
shipeasy.add_extras(order_id=order.id, tenant=tenant.slug)

# ...deep in a service, later in the same request...
try:
    charge(order)
except PaymentError as e:
    # report carries order_id + tenant automatically; a chained .extras / .to
    # extra of the same key wins over the ambient one.
    shipeasy.see(e).causes_the("checkout").to("use cached prices")
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
