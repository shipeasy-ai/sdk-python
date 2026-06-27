Check a kill switch on a user-bound client. Assumes `configure()` ran at
startup — see Installation.

### Top-level guard

```python
import shipeasy

# construct once per callsite (cheap; binds the user)
client = shipeasy.Client(current_user)

# name                          kill switch name (required)
if client.get_killswitch("{{KILLSWITCH_KEY}}"):  # True == engaged (feature killed)
    return fallback()
```

### Named switch — check one configured per-key switch

```python
import shipeasy

client = shipeasy.Client(current_user)

# switch_key                    the variable you check against the switches
#                               CONFIGURED on the kill switch (dashboard "switches");
#                               if that key isn't configured, falls back to the
#                               top-level value above
provider = "stripe"
if client.get_killswitch("{{KILLSWITCH_KEY}}", provider):
    return use_backup_processor()   # the "stripe" switch is engaged
```
