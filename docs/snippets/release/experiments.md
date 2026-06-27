Read an experiment, then track its success event.

```python
import shipeasy

engine = shipeasy.configure(api_key="sdk_server_...")

result = shipeasy.Client(current_user).get_experiment(
    "{{RESOURCE_NAME}}", default_params={"color": "blue"}
)
if result.params["color"] == "green":
    ...

engine.track(current_user.id, "{{SUCCESS_EVENT}}", {"amount": 49})
```
