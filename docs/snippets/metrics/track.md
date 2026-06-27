Track a metric/conversion event from the bound client. Metrics in the dashboard
are computed from these events. Assumes `configure()` ran at startup — see
Installation.

### Track an event

```python
import shipeasy

# construct once per callsite (cheap; binds the user)
client = shipeasy.Client(current_user)

# event_name                    the event your metric is built on (required)
# properties={...}              optional payload; numeric/string fields you can
#                               sum/filter on in a metric (private attributes are
#                               stripped before the event leaves the process)
client.track("{{EVENT_NAME}}", {"amount": 49, "currency": "usd"})
```

Fire-and-forget (never blocks your response) and a no-op under
`configure_for_testing` / `configure_for_offline`. The unit is the bound user
(`user_id`, else `anonymous_id`); with no unit the call is a no-op.

### Track without properties

```python
import shipeasy

client = shipeasy.Client(current_user)

client.track("{{EVENT_NAME}}")   # properties are optional
```
