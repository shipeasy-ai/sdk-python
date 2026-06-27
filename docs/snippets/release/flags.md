Configure once, then read a flag on a user-bound client.

```python
import shipeasy

shipeasy.configure(api_key="sdk_server_...")

if shipeasy.Client(current_user).get_flag("{{RESOURCE_NAME}}"):
    ...
```
