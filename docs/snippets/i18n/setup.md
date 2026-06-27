This is a server SDK: it has no `t()`. During SSR, emit the i18n loader tag
(public CLIENT key) so the browser SDK boots against the `{{PROFILE}}` profile.
Assumes `configure()` ran at startup — see Installation.

```python
import shipeasy

# Package-level helper — delegates to the engine configured at startup.
# client_key                    PUBLIC client key (sdk_client_...) — NOT the server key
# profile="en:prod"             locale profile to boot the browser SDK against
# base_url=...                  optional: override the CDN origin (default cdn.shipeasy.ai)
head = shipeasy.i18n_script_tag(client_key, "{{PROFILE}}")  # goes in <head>
```
