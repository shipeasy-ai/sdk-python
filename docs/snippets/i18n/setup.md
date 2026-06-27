This is a server SDK: it has no `t()`. During SSR, emit the i18n loader tag
(public CLIENT key) so the browser SDK boots against the `{{PROFILE}}` profile.
Assumes `configure()` ran at startup — see Installation.

```python
import shipeasy

# the shared Engine built at startup (configure() returns it; or get_global_engine())
engine = shipeasy.get_global_engine()

# client_key                    PUBLIC client key (sdk_client_...) — NOT the server key
# profile="en:prod"             locale profile to boot the browser SDK against
# base_url=...                  optional: override the CDN origin (default cdn.shipeasy.ai)
head = engine.i18n_script_tag(client_key, "{{PROFILE}}")  # goes in <head>
```
