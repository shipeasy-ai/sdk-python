# Advanced

## Anonymous-id bucketing + middleware

For logged-out traffic you need a *stable* unit so a fractional rollout buckets
the same on the server and in the browser. The middleware mints a first-party
`__se_anon_id` cookie (shared with every Shipeasy SDK) for any request without
one; evaluations then **default to it** as `anonymous_id`, so `get_flag` on an
anonymous request just works — no per-call wiring.

```python
# WSGI (Flask, Django, ...)
from shipeasy.middleware import AnonIdMiddleware
app.wsgi_app = AnonIdMiddleware(app.wsgi_app)

# ASGI (FastAPI, Starlette)
from shipeasy.middleware import AnonIdASGIMiddleware
app.add_middleware(AnonIdASGIMiddleware)
```

```python
# logged-out request → buckets on the __se_anon_id cookie automatically
client = shipeasy.Client({})
client.get_flag("new_checkout")
```

An explicit `user_id`/`anonymous_id` always wins. The id is also on the request
(`environ["shipeasy.anon_id"]`). The cookie is non-`HttpOnly` by design so the
browser SDK buckets identically; a request with **no** unit still resolves a
fully-rolled (100%) gate as on. Cookie name + format are a cross-SDK contract.

## Private attributes

Pass `private_attributes` to [`configure()`](configuration.md) to strip the named
keys from every outbound event `properties` bag before it POSTs to `/collect`
(`privateAttributes`). The server evaluates locally, so private attrs
**still drive targeting** — they just never leave the process on the telemetry
path:

```python
shipeasy.configure(api_key="sdk_server_...", private_attributes=["email", "ssn"])
```

## Sticky bucketing

Pass a `sticky_store` to `configure()` to pin a user's experiment assignment
across allocation changes. `InMemoryStickyStore` is built in; implement the
`StickyBucketStore` protocol (`get(unit)` / `set(unit, exp, entry)`) for a
durable backend:

```python
from shipeasy import InMemoryStickyStore

shipeasy.configure(api_key="sdk_server_...", sticky_store=InMemoryStickyStore())
```

Absent a store, bucketing is deterministic (MurmurHash3 over the unit).

## Bucketing unit (`bucketBy`)

The bucketing unit per experiment is **server-driven**: an experiment can be
configured to bucket on a non-default attribute (e.g. `company_id`) in the
dashboard, and the SDK reads it from the experiment definition
(`exp.bucketBy`) — falling back to `user_id` then `anonymous_id`. Make sure that
attribute is present in the user map you pass.

## Exposure on read

There is no manual exposure primitive. Reading an assignment **is** the exposure:
`assign()` is side-effect free, and an enrolled `Assignment` logs a single
`exposure` event the **first time you read a param** via `.get()` — on the same
bound `Client`, no user argument:

```python
# construct once per callsite (cheap; binds the user)
client = shipeasy.Client(current_user)

a = client.universe("checkout").assign()        # no exposure yet
color = a.get("button_color", "red")            # first read → logs one exposure
peek = a.get("button_color", "red", exposure=False)   # peek, logs nothing
```

Exposures are deduped per process (by unit + experiment + group) **and** durably
per `(unit, experiment, group)` server-side, so repeated reads — and repeated
`assign()`/`get()` across requests — don't spam the collector. No-op in
test/offline mode or when the unit isn't enrolled.

## Server-side rendering (SSR)

Emit the request's evaluated flags as a declarative `<script>` tag so the
browser SDK has them on first paint. `shipeasy.bootstrap_script_tag` carries the
payload in `data-*` attributes (**no key**); the `/sdk/runtime.js` browser
runtime reads them, installs `window.shipeasy`, republishes
`window.__SE_BOOTSTRAP` for the npm client SDK and writes the `__se_anon_id`
cookie so the browser buckets identically to the server. Both helpers delegate to the engine
configured via `configure()` — you never touch it directly.

```python
import shipeasy

user = {"user_id": "u_123"}

# Two tags for the document <head>. The PUBLIC client key (not the server key)
# goes on the i18n loader tag — and it comes from configure(), so the callsite
# does not repeat it.
head = shipeasy.bootstrap_script_tag(user, anon_id=anon_id) \
     + shipeasy.i18n_script_tag()
```

### Every argument is optional

All three tag helpers fall back to what `configure()` already set, so the bare
call is the normal one — pass an argument only to override the configured value
for that one tag:

| Helper | Signature | Defaults |
| --- | --- | --- |
| `shipeasy.i18n_script_tag` | `(client_key=None, profile=None, *, base_url=None)` | `client_key`, `profile`, `cdn_base_url` |
| `shipeasy.bootstrap_script_tag` | `(user=None, *, anon_id=None, i18n_profile=None, base_url=None)` | anonymous request, no anon id, `profile`, `cdn_base_url` |
| `shipeasy.devtools_script_tag` | `(project_id=None, *, client_key=None, base_url=None, defer=True)` | `project_id`, `client_key`, `cdn_base_url` |

```python
shipeasy.configure(
    api_key=os.environ["SHIPEASY_SERVER_KEY"],
    client_key=os.environ["SHIPEASY_CLIENT_KEY"],   # PUBLIC key, for the tags
    project_id=os.environ["SHIPEASY_PROJECT_ID"],   # for the devtools tag
    profile="en:prod",
)
```

A tag still renders when a value is missing (the browser bundle reports what it
needs), but the SDK logs a warning naming the `configure()` option to fill in —
once per option, not once per render.

### Devtools overlay tag

`shipeasy.devtools_script_tag()` emits the hosted devtools overlay bundle —
nothing to install, no overlay code in your bundle. It reads the project id and
public client key off the tag and opens with **Shift+Alt+S** or on any page
loaded with `?se=1`. It is `defer`red by default: a developer tool never belongs
on the critical rendering path.

```python
head += shipeasy.devtools_script_tag()
```

Adding it unconditionally is fine: the overlay only opens for someone with a
signed-in Shipeasy session, so on a page where nobody has authenticated it
renders nothing and says nothing. Gating it on your own staff or environment
check is **optional** — worth it only if you'd rather the bundle not load for
end users at all:

```python
head += shipeasy.devtools_script_tag() if request.user.is_staff else ""
```

### DevTools overrides on server reads

A signed-in DevTools overlay mirrors every override — including `?se_gate_x=true`
URL state — into a signed `se_ov` cookie that rides every same-origin request.
Install the middleware (or scope the request yourself) and server-side
`Client` reads honor it: `get_flag` / `get_flag_detail` (reason `OVERRIDE`),
`get_killswitch` (whole-switch reads), `get_config`, and
`universe(name).assign()` experiment groups.

```python
# Already using AnonIdMiddleware / AnonIdASGIMiddleware / the Django middleware?
# Nothing to add — they verify the cookie once per request. Otherwise scope it
# by hand around the work that reads flags:
with shipeasy.request_overrides(request.headers.get("Cookie")):  # a Cookie header or the bare se_ov value
    client = shipeasy.Client(user)
    client.get_flag("new_checkout")  # True if the signed cookie forces it
```

Precedence: `override_flag` / `override_config` / `override_experiment` >
signed cookie > normal evaluation. It is **fail-closed**: overrides apply only
when Shipeasy serves your project's override key, the signature verifies, the
key id matches and the cookie has not expired — otherwise reads resolve
normally and nothing raises. Outside a `request_overrides` scope behaviour is
unchanged. A bare, unsigned `?se_gate_` URL param is client-only by design and
never reaches the server.

#### Frontend and API on different subdomains

With the frontend on `app.example.com` and the API on `api.example.com`, the
browser SDK scopes the override cookies to the registrable domain
(auto-detected; override with the browser `overrideCookieDomain` option), so the
API receives them as ordinary cookies. For token-auth APIs that do not take
cookies, the browser SDK's `getOverrideHeaders()` returns an
`X-Shipeasy-Overrides` header (cookie syntax, e.g. `se_ov=<v>; se_ov_dev=<v>`)
to send on API calls; the API's CORS must allow that header. The middleware reads
it automatically; with the manual scope pass it as the second argument:

```python
with shipeasy.request_overrides(
    request.headers.get("Cookie"),
    request.headers.get("X-Shipeasy-Overrides"),  # optional; the Cookie header wins per cookie name
):
    ...
```

The same verification and guards apply to the header: signed cookies must
verify, and `se_ov_dev` is not even parsed unless `dev_overrides` is on in a
non-production process.

#### Dev-only URL overrides without DevTools sign-in

On a local/dev/test stack you can opt in to the unsigned `se_ov_dev` cookie the
browser SDK mirrors from `?se_gate_x=true`-style URL params, so URL overrides
reach server reads with no DevTools sign-in:

```python
shipeasy.configure(api_key=..., dev_overrides=True)  # default False
```

Two guards, both required: the option is `True` **and** the process is not
production (`SHIPEASY_ENV` / `APP_ENV` / `ENV` / `PYTHON_ENV`, else the `env`
option; `configure_for_testing` counts as non-production). In a production
process the option is ignored with one warning, and the cookie is never even
read — it is never active in production. Precedence: `override_*` > signed
`se_ov` > `se_ov_dev` > evaluation (per name; signed wins conflicts).

### Identity coherence (no anon→identified flip)

When you pass an identified `user` (one carrying `user_id` / `email` / targeting
traits, not just an `anonymous_id`), those traits also ride the tag as
`data-user`. The browser SDK **adopts** that identity on first paint — its flags
are already this user's, and a later `identify()` in the browser reconciles
**idempotently** (a matching call is a no-op, no extra `/sdk/evaluate`, no
flip). Because the server already evaluated the payload for this user, the
`data-flags` on the tag match what the client would compute, so there is no
anon→identified flip. An anonymous request (only `anonymous_id`, or no traits)
emits no `data-user`, so the tag carries no PII when there is no identity to
carry.
