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

Besides its single top-level on/off value, a kill switch can carry **named
per-key switches** — independently-flippable booleans, each under a key you
choose (one per payment provider, region, vendor, …). These are **configured on
the kill switch itself** (in the dashboard "switches" feature, or in an offline
snapshot — see below); the SDK only *reads* them. They do not exist until you add
them.

Pass that key as the second argument, `switch_key`, to check **one named switch**
instead of the top-level value. The natural pattern is to pass *the thing you're
about to do* as the key, and let the kill switch decide:

```python
provider = "stripe"   # the variable you check against the configured switches

# construct once per callsite (cheap; binds the user)
client = shipeasy.Client(current_user)

if client.get_killswitch("payments_circuit_breaker", provider):
    # the "stripe" switch is engaged → skip Stripe, take the fallback
    return use_backup_processor()
```

Resolution order for `get_killswitch(name, switch_key)`:

1. If the kill switch has a named switch matching `switch_key`, **that switch's
   boolean is returned**.
2. Otherwise — the key isn't configured on the kill switch — it **falls back to
   the top-level value**. So an unknown/unconfigured key behaves exactly like
   `get_killswitch(name)` with no key.

That fallback lets you wire the key everywhere first and turn individual switches
on later: until you actually add the `"stripe"` switch, every
`get_killswitch("payments_circuit_breaker", "stripe")` just reflects the kill
switch's overall state.

### Configuring switches for a test

In production these are set in the dashboard. To exercise them in a test, put a
`switches` map on the kill switch in an [offline snapshot](testing.md):

```python
shipeasy.configure_for_offline(snapshot={
    "flags": {
        "gates": {}, "configs": {},
        "killswitches": {
            "payments_circuit_breaker": {
                "value": False,                       # top-level (fallback)
                "switches": {"stripe": True, "paypal": False},
            }
        },
    },
    "experiments": {},
})

c = shipeasy.Client({"user_id": "u_1"})
assert c.get_killswitch("payments_circuit_breaker") is False           # top-level
assert c.get_killswitch("payments_circuit_breaker", "stripe") is True  # named switch
assert c.get_killswitch("payments_circuit_breaker", "paypal") is False
assert c.get_killswitch("payments_circuit_breaker", "other") is False  # falls back
```

Kill switches are also folded into normal gate evaluation; `get_killswitch` is
the explicit read of that same state.
