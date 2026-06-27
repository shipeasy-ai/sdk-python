This is a server SDK: it has no `t()`. During SSR, emit the i18n loader tag
(public CLIENT key) so the browser SDK boots against the `{{PROFILE}}` profile.

```python
# engine is the Engine from shipeasy.configure(...)
head = engine.i18n_script_tag(client_key, "{{PROFILE}}")  # goes in <head>
```
