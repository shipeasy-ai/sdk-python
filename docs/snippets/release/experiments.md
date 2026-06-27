Read an experiment, then track its success event.

```python
import shipeasy

shipeasy.configure(api_key="sdk_server_...")

client = shipeasy.Client(current_user)
result = client.get_experiment("{{RESOURCE_NAME}}", default_params={"color": "blue"})
client.log_exposure("{{RESOURCE_NAME}}")
if result.params["color"] == "green":
    ...

client.track("{{SUCCESS_EVENT}}", {"amount": 49})
```
