This is a server SDK: it has no `t()`. During SSR, emit the i18n loader tag
(public CLIENT key) so the browser SDK boots against the `{{PROFILE}}` profile.
Assumes `configure()` ran at startup — see Installation.

### i18n loader tag only

```python
import shipeasy

# Package-level helper — delegates to the engine configured at startup.
# client_key                    PUBLIC client key (sdk_client_...) — NOT the server key
# profile="en:prod"             locale profile to boot the browser SDK against
# base_url=...                  optional: override the CDN origin (default cdn.shipeasy.ai)
head = shipeasy.i18n_script_tag(client_key, "{{PROFILE}}")  # goes in <head>
```

### Flags bootstrap + i18n together

```python
import shipeasy

user = {"user_id": "u_123"}

# bootstrap_script_tag carries the evaluated flags (NO key); i18n_script_tag adds
# the loader (public client key). Both go in <head>.
# anon_id=...                   the request's __se_anon_id, so the browser buckets identically
# i18n_profile=...              fold the i18n profile into the bootstrap tag instead
head = shipeasy.bootstrap_script_tag(user, anon_id=anon_id) \
     + shipeasy.i18n_script_tag(client_key, "{{PROFILE}}")
```
