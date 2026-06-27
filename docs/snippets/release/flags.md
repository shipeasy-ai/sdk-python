Read a feature flag on a user-bound client. Assumes `configure()` ran at
startup — see Installation.

### Basic check

```python
import shipeasy

# construct once per callsite (cheap; binds the user)
client = shipeasy.Client(current_user)

# name                          flag name (required)
# default=False                 returned ONLY when the flag can't be evaluated
#                               (client not ready / flag absent) — never when it
#                               simply resolves off
if client.get_flag("{{FLAG_KEY}}", default=False):
    ...
```

### Why it resolved that way — `get_flag_detail`

```python
import shipeasy

client = shipeasy.Client(current_user)

# returns FlagDetail(value, reason); reason ∈ RULE_MATCH / DEFAULT / OFF /
# OVERRIDE / FLAG_NOT_FOUND / CLIENT_NOT_READY
detail = client.get_flag_detail("{{FLAG_KEY}}")
log.info("flag=%s value=%s reason=%s", "{{FLAG_KEY}}", detail.value, detail.reason)
```

### React to flag changes (long-running server)

```python
import shipeasy

# requires configure(poll=True); fires after a poll fetches NEW data (200, not 304)
unsubscribe = shipeasy.on_change(lambda: rebuild_local_cache())
# ... later: unsubscribe()
```
