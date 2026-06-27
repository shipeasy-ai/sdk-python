# Kill switches — `get_killswitch`

A kill switch is an admin resource that ships in the flags blob alongside gates
and configs. `get_killswitch` reads it and returns a boolean. No telemetry is
emitted for a kill-switch read. After [`configure()`](configuration.md), read it
through the bound `shipeasy.Client(user)`.

```python
# construct once per callsite (cheap; binds the user)
client = shipeasy.Client(current_user)

if client.get_killswitch("payments_circuit_breaker"):
    # the kill switch is engaged — short-circuit the risky path
    return fallback()
```

## Named switches

A kill switch can carry per-key override **switches**. Pass the optional
`switch_key` to read one named switch instead of the top-level value:

```python
client.get_killswitch("payments_circuit_breaker", "stripe")
```

Kill switches are also folded into normal gate evaluation; `get_killswitch` is
the explicit read of that same state.
