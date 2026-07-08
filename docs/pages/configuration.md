# Configuration

## `configure(...)` — the once-per-process call

```python
import shipeasy

shipeasy.configure(
    api_key="sdk_server_...",
    attributes=lambda u: {"user_id": u.id, "country": u.country, "plan": u.plan},
)
```

- **`api_key`** — your Shipeasy **server key** (`sdk_server_...`). Authenticates
  flags, configs, kill switches and experiments. Never embed it in a browser.
- **`attributes`** — a transform from YOUR user object to the Shipeasy attribute
  map that targeting evaluates against. The default is identity, so if your user
  object is already that map you can omit it:

  ```python
  shipeasy.configure(api_key="sdk_server_...")
  # construct once per callsite (cheap; binds the user)
  client = shipeasy.Client({"user_id": "u_123", "country": "US"})
  client.get_flag("new_checkout")
  ```

`configure()` is first-config-wins: the first call wires everything up; later
calls are a no-op. By default it kicks off a one-shot fetch fire-and-forget, so
the first `Client(user).get_flag(...)` resolves against real rules.

## Identity default

The attribute map you produce is the **unit of identity** — supply `user_id`
for logged-in users, or let the [anon-id middleware](advanced.md) inject
`anonymous_id` for logged-out traffic. An explicit `user_id`/`anonymous_id`
always wins.

## One-shot vs background poll

- **default** (`init=True`) — a one-shot fetch. Ideal for serverless / short-lived
  processes.
- **`poll=True`** — start the **background poll** (initial fetch + periodic
  refresh) for a long-running server, so flags stay fresh without a redeploy.
  Configuration owns the lifecycle; you never touch a lower-level object:

```python
shipeasy.configure(api_key="sdk_server_...", poll=True)
```

## `configure()` options

Any of these pass straight through `configure(...)` as keyword arguments:

| keyword | type | default | what it does |
| --- | --- | --- | --- |
| `attributes` | `Callable` | identity | YOUR user object → the Shipeasy attribute map. |
| `init` | `bool` | `True` | Fire the one-shot fetch fire-and-forget. |
| `poll` | `bool` | `False` | Start the background poll (refreshes the blob over time). |
| `base_url` | `str` | `https://api.shipeasy.ai` | API base URL for the blobs. Override for a self-hosted edge or in tests. |
| `env` | `str` | `"prod"` | Deployment environment tag, attached to `see()` error events and usage telemetry. |
| `disable_telemetry` | `bool` | `False` | Opt out of per-evaluation usage telemetry. Evaluation itself is unaffected. |
| `telemetry_url` | `str` | built-in | Override the telemetry endpoint (rarely needed). |
| `private_attributes` | `Sequence[str]` | `[]` | Attribute keys stripped from every outbound event before it leaves the process. They still drive **targeting** locally. See [advanced](advanced.md). |
| `sticky_store` | `StickyBucketStore` | `None` | Pin a user's experiment group across re-buckets. See [advanced](advanced.md). |
| `log_level` | `str` | `"warn"` | Verbosity of the SDK's own internal diagnostics. See below. |
| `disable_internal_error_reporting` | `bool` | `False` | Opt out of SDK self-monitoring (see below). Your `see()` reporting is unaffected. |

## Fail-safe reads & the `log_level` option

The runtime read/track methods on `shipeasy.Client(user)` —
`get_flag` / `get_flag_detail` / `get_config` / `get_experiment` /
`get_killswitch` / `track` / `log_exposure`, and the `see()` reporting chain —
**never raise into your request path.** If anything goes wrong internally (a bad
`decode` callback, an unexpected error), the SDK logs it and returns the safe
default instead: your `default` for `get_flag`/`get_config`, a not-enrolled
`control` result for `get_experiment`, `False` for `get_killswitch`, and a no-op
for `track`/`log_exposure`. A feature-flag lookup can't be the thing that takes
down a request.

Setup still raises loudly — that's boot-time misconfiguration you want to see:
constructing `Client(user)` before `configure()`, `configure_for_offline` with no
source, `Engine.from_file` on a bad path/JSON, and errors thrown by your own
`attributes` transform.

`log_level` tunes the SDK's own diagnostic logging (via the `shipeasy` logger).
Accepted values, least → most verbose:

```
silent  <  error  <  warn  <  info  <  debug
```

A message logged at level `L` is emitted iff the configured level is at least
`L` — so the default `"warn"` shows `error` + `warn` and mutes `info` + `debug`,
and `"silent"` mutes everything. An unknown value is ignored (keeps `"warn"`).
This only affects log output; it never changes the fail-safe behaviour above.

```python
shipeasy.configure(api_key="sdk_server_...", log_level="silent")
```

## SDK self-monitoring

When one of those last-resort guards swallows an **internal** SDK failure — a bug
on Shipeasy's side, not yours — the SDK also reports that error to Shipeasy's own
project, so we can find and fix SDK bugs across every app the SDK runs in. This is
a dedicated, baked-in destination entirely separate from your own `see()`
reporting: **internal errors never land in your project or Errors tab.** The
report carries only the error plus a stable, deduped consequence (the guarded
operation, e.g. `flags.get`) and is fire-and-forget, so it can never slow down or
break a read.

It is on by default and off automatically in `configure_for_testing` /
`configure_for_offline`. To opt out entirely:

```python
shipeasy.configure(api_key="sdk_server_...", disable_internal_error_reporting=True)
```

## Tests and offline

For unit tests and offline evaluation, use the drop-in siblings of `configure()`
— [`configure_for_testing` / `configure_for_offline`](testing.md). They take the
same `attributes` transform (and override args), skip the api key, and let
`shipeasy.Client(user)` read without ever touching the network.
