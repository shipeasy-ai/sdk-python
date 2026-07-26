This is a server SDK: it has no `t()`. During SSR, emit the i18n loader tag
(public CLIENT key) so the browser SDK boots against the `{{PROFILE}}` profile.
Assumes `configure()` ran at startup — see Installation.

### i18n loader tag only

```python
import shipeasy

# Package-level helper — delegates to the engine configured at startup.
# EVERY argument is optional and falls back to configure():
# client_key=None               PUBLIC client key (sdk_client_...) — NOT the server key
#                               (default: the configured client_key)
# profile=None                  locale profile to boot the browser SDK against
#                               (default: the configured profile, else "en:prod")
# base_url=None                 CDN origin (default: the configured cdn_base_url)
head = shipeasy.i18n_script_tag()  # goes in <head>
```

### Devtools overlay tag

```python
import shipeasy

# Hosted se-devtools.js overlay — opens with Shift+Alt+S or ?se=1.
# project_id=None               your project id (default: the configured project_id)
# client_key=None               PUBLIC client key (default: the configured client_key)
# base_url=None                 CDN origin (default: the configured cdn_base_url)
# defer=True                    keep the overlay off the critical rendering path
head += shipeasy.devtools_script_tag()
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
     + shipeasy.i18n_script_tag()
```
