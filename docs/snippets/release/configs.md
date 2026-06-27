Read a dynamic config on a user-bound client. Assumes `configure()` ran at
startup — see Installation.

```python
import shipeasy

# construct once per callsite (cheap; binds the user)
client = shipeasy.Client(current_user)

# name                          config name (required)
# decode=lambda v: ...          optional: transform the raw JSON value (typed)
# default={}                    returned when the key is absent or decode raises
config = client.get_config("{{RESOURCE_NAME}}", default={})

# typed example:
# max_items = client.get_config("{{RESOURCE_NAME}}", decode=lambda v: v["max"], default=0)
```
