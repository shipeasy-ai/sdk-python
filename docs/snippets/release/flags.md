Read a feature flag on a user-bound client. Assumes `configure()` ran at
startup — see Installation.

```python
import shipeasy

# construct once per callsite (cheap; binds the user)
client = shipeasy.Client(current_user)

# name                          flag name (required)
# default=False                 returned ONLY when the flag can't be evaluated
#                               (client not ready / flag absent) — never when it
#                               simply resolves off
if client.get_flag("{{RESOURCE_NAME}}", default=False):
    ...
```
