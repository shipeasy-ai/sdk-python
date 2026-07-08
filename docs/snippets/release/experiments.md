Ask a universe for an assignment (a unit lands in ≤1 experiment; exposure is
auto-logged on an enrolled assign), then track its success event. Assumes
`configure()` ran at startup — see Installation.

```python
import shipeasy

# construct once per callsite (cheap; binds the user)
client = shipeasy.Client(current_user)

# universe name (required) — a mutual-exclusion pool of experiments.
# assign() takes NO user arg: it uses the bound user and auto-logs one exposure.
a = client.universe("{{EXPERIMENT_KEY}}").assign()

# a.name      -> the experiment the unit landed in, or None
# a.group     -> the assigned variant, or None
# a.enrolled  -> bool (group is not None)
# a.get(field, fallback) -> variant override -> universe default -> fallback
if a.get("color") == "green":
    ...

# track the conversion on the same bound client; unit is the bound user
# event_name                    success event (required)
# properties={...}              optional event properties bag
client.track("{{SUCCESS_EVENT}}", {"amount": 49})
```
