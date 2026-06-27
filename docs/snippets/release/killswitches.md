Check a kill switch on a user-bound client. Assumes `configure()` ran at
startup — see Installation.

```python
import shipeasy

# construct once per callsite (cheap; binds the user)
client = shipeasy.Client(current_user)

# name                          kill switch name (required)
# switch_key="..."              optional: read a named per-key override
#                               (the dashboard "switches" feature); falls back
#                               to the top-level value when absent
if client.get_killswitch("{{RESOURCE_NAME}}"):  # True == engaged (feature killed)
    return fallback()
```
