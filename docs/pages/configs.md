# Dynamic configs — `get_config`

A config is a typed JSON value with targeting. `get_config` returns the resolved
value for the bound (or passed) user.

## Bound `Client(user)` form

```python
client = shipeasy.Client(current_user)
config = client.get_config("billing_copy")
```

## Low-level `Engine` form

```python
config = engine.get_config("billing_copy")
```

## Defaults

`get_config` takes a `default` that is returned when the config key is **absent**
(or a `decode` raises):

```python
engine.get_config("billing_copy", default={"title": "Welcome"})
```

## Typed decode

Pass a `decode` callable to project the raw JSON value into the shape you want.
It still applies on top of overrides; if it raises, the `default` is returned:

```python
engine.get_config("limits", decode=lambda v: v["max"], default=0)
```
