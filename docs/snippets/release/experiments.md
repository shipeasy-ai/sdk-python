Read an experiment, log exposure where you present the treatment, then track its
success event. Assumes `configure()` ran at startup — see Installation.

```python
import shipeasy

# construct once per callsite (cheap; binds the user)
client = shipeasy.Client(current_user)

# name                          experiment name (required)
# default_params={...}          params returned when the user isn't enrolled
# decode=lambda p: ...          optional: transform the params bag (typed)
result = client.get_experiment("{{EXPERIMENT_KEY}}", default_params={"color": "blue"})

# call where you actually render the treatment (server is stateless — no auto-log)
client.log_exposure("{{EXPERIMENT_KEY}}")  # experiment name (required)

if result.params["color"] == "green":
    ...

# track the conversion on the same bound client; unit is the bound user
# event_name                    success event (required)
# properties={...}              optional event properties bag
client.track("{{SUCCESS_EVENT}}", {"amount": 49})
```
