Read a dynamic config on a user-bound client. Assumes `configure()` ran at
startup — see Installation.

### Raw value

```python
import shipeasy

# construct once per callsite (cheap; binds the user)
client = shipeasy.Client(current_user)

# name                          config name (required)
# default={}                    returned when the key is absent (or decode raises)
config = client.get_config("{{CONFIG_KEY}}", default={})
```

### Typed decode

```python
import shipeasy

client = shipeasy.Client(current_user)

# decode=lambda v: ...          transform the raw JSON value into the shape you want;
#                               applied on top of overrides — if it raises, default is returned
max_items = client.get_config("{{CONFIG_KEY}}", decode=lambda v: v["max"], default=0)
```
