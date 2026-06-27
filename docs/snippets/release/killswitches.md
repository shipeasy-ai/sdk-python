Check a kill switch on a user-bound client.

```python
import shipeasy

shipeasy.configure(api_key="sdk_server_...")

if shipeasy.Client(current_user).get_killswitch("{{RESOURCE_NAME}}"):
    return fallback()
```
