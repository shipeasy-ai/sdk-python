# Dynamic configs — `get_config`

A config is a typed JSON value with targeting. After
[`configure()`](configuration.md), read it through the bound
`shipeasy.Client(user)`.

```python
# construct once per callsite (cheap; binds the user)
client = shipeasy.Client(current_user)

config = client.get_config("billing_copy")
```

## Defaults

`get_config(name, decode=None, default=None)` returns `default` when the config
key is **absent** (or a `decode` raises):

```python
client.get_config("billing_copy", default={"title": "Welcome"})
```

## Typed decode

Pass a `decode` callable to project the raw JSON value into the shape you want.
It applies on top of any override; if it raises, the `default` is returned:

```python
client.get_config("limits", decode=lambda v: v["max"], default=0)
```
