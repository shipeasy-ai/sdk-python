Read a dynamic config on a user-bound client.

```python
import shipeasy

shipeasy.configure(api_key="sdk_server_...")

config = shipeasy.Client(current_user).get_config("{{RESOURCE_NAME}}", default={})
```
