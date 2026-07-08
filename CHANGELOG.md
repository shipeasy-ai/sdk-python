# Changelog

## 0.14.1 (2026-07-07)

### Fixed

- **Default API host now resolves.** The default `base_url` pointed at the
  unregistered domain `https://edge.shipeasy.dev`, so every `configure()`
  one-shot fetch and every `get_flag`/`get_config`/`get_experiment`/`track`/
  `see()` call failed with a DNS error unless `base_url` was set explicitly.
  Corrected to the real edge origin `https://api.shipeasy.ai` — the host the
  docs, CLI, and curl snippets already use. Explicit `base_url` overrides are
  unaffected.

## 0.14.0 (2026-07-07)

- **Runtime methods never raise into the caller.** Every runtime read/track/see
  method — `get_flag`, `get_flag_detail`, `get_config`, `get_experiment`,
  `get_killswitch`, `track`, `log_exposure`, and the `see()` chain — is now
  wrapped in a defensive guard on both `Engine` and the bound `Client`. On any
  unexpected internal error the SDK logs and returns the documented safe default
  (flags → your `default`, configs → `default`, experiments → a not-enrolled
  `control` result, kill switches → `False`, track/exposure → no-op) instead of
  propagating. Setup/lifecycle calls (`Client()` before `configure()`,
  `configure_for_offline` with no source, `Engine.from_file` on a bad path/JSON,
  the user `attributes` transform) still raise loudly — that's boot-time
  misconfiguration and must stay visible.
- **New `log_level` option.** `configure(..., log_level="warn")` (and the
  `configure_for_testing` / `configure_for_offline` siblings, and
  `Engine(..., log_level=...)`) tunes the SDK's own internal diagnostics — one of
  `"silent" | "error" | "warn" | "info" | "debug"` (ordered
  `silent < error < warn < info < debug`; a message at level L shows iff the
  configured level is >= L). Default `"warn"`; an unknown value is ignored. All
  internal diagnostic logging now routes through a small leveled logger and is
  gated by this option. Logging never raises.

## 0.13.1

- **Admin API client regenerated from the canonical OpenAPI spec (2.0.0).** The
  0.13.0 client was generated from a stale 1.0.0 subset; this regenerates it from
  the full spec, adding the connectors, errors, keys, drafts, profiles and
  api-keys endpoints. `AdminClient` resource groups now track the spec tags:
  `flags`, `configs`, `killswitch`, `experiments`, `universes`, `attributes`,
  `metrics`, `events`, `ops`, `alerts`, `projects`, `profiles`, `keys`, `drafts`,
  `errors`, `connectors`, `api_keys` (renamed from `gates`/`killswitches`/
  `alert_rules`, plus the new groups).

## 0.13.0 (2026-06-28)

- **Optional Admin API client** — a new opt-in `shipeasy.admin` subpackage for
  *administering* resources (create gates, start experiments, manage configs/
  killswitches/universes/metrics/events, …) from server code. It is a raw client
  **generated from the Shipeasy OpenAPI spec** (1:1 with the REST API — id-based,
  basis-points, snake_case; no name->id or percent->bp ergonomics, which stay in
  the CLI/MCP).
  - Off by default: the base SDK never imports it. Opt in with
    `pip install "shipeasy[admin]"` (pulls `urllib3`/`pydantic`/`python-dateutil`).
  - `from shipeasy.admin import AdminClient` — a thin auth/scoping wrapper:
    `AdminClient(api_key=..., project_id=...)` then `admin.gates.list_gates()`,
    `admin.experiments.create_experiment(...)`, etc. (resource groups: gates,
    configs, killswitches, experiments, universes, metrics, events, alert_rules,
    attributes, projects, ops, i18n).
  - Regenerate after a contract change: refresh `admin/openapi.json` then run
    `bash scripts/gen_admin.sh` (only `shipeasy/admin/generated/` is rewritten;
    the `AdminClient` shim is preserved). Generator pinned via `openapitools.json`.

## 0.12.0 (2026-06-28)

- **Django integration** — a new `shipeasy.django` app + a
  `python manage.py shipeasy_install` management command, the Django-native
  equivalent of the Rails install generator.
  - Add `"shipeasy.django"` to `INSTALLED_APPS` and the app's
    `ShipeasyConfig.ready()` reads a `SHIPEASY` settings dict and calls
    `configure()` once at boot (keys: `SERVER_KEY` required, `ATTRIBUTES`
    (dotted import path or callable), `ENV`, `DISABLE_TELEMETRY`,
    `PRIVATE_ATTRIBUTES`, `BASE_URL`, `POLL` (default `False`)). Missing
    `SERVER_KEY` warns and no-ops.
  - `shipeasy.django.middleware.AnonIdMiddleware` — a Django-style middleware
    (add to `MIDDLEWARE`) that mints/reads the shared `__se_anon_id` cookie,
    reusing the cross-SDK anon-id helpers.
  - `python manage.py shipeasy_install` idempotently patches the settings file
    (adds the app to `INSTALLED_APPS`, the middleware to `MIDDLEWARE`, and a
    `SHIPEASY = {...}` block) and appends `SHIPEASY_SERVER_KEY=` to an existing
    `.env` / `.env.example`. Anchored edits with a safe print-to-paste fallback;
    flags `--settings-file`, `--force`, `--no-env`.
  - Django is a dev/optional dependency only (a `django` extra) — the base SDK
    never imports Django, and `shipeasy.django` imports it lazily.

## 0.11.0 (2026-06-27)

- New package-level on-the-spot override helpers `override_flag()`,
  `override_config()`, `override_experiment()` and `clear_overrides()` for
  flipping values mid-test on top of `configure_for_testing` /
  `configure_for_offline`.
- New **`shipeasy-skill`** console command — `shipeasy-skill install` copies the
  bundled agent skill (`SKILL.md`) into your project's skills directory
  (default `.claude/skills/shipeasy-python/`); `shipeasy-skill print` writes it
  to stdout. An explicit opt-in (Python packaging has no safe post-install hook).

## 0.10.0 (2026-06-27)

- Add `configure_for_testing()` and `configure_for_offline()` — drop-in siblings
  of `configure()` for unit tests and offline evaluation. Both take the same
  `attributes` transform (no api key needed) and accept `flags` / `configs` /
  `experiments` override args, then register the global engine so
  `shipeasy.Client(user)` reads against them. They **replace** any prior
  configuration so tests can reconfigure between cases.
- `configure()` gains a `poll=True` option to start the background poll
  internally (no need to call `init()` on a returned object).
- New package-level helpers `on_change()`, `i18n_script_tag()` and
  `bootstrap_script_tag()` delegate to the configured global engine, and
  `ShipeasyProvider()` now resolves it automatically — so the **`Engine` class is
  an internal detail**: the docs are written entirely around `configure()` +
  `shipeasy.Client(user)`. The `Engine` class and its methods remain available
  for advanced use (no breaking change).

## 0.9.0 (2026-06-27)

- Add `track()`/`log_exposure()` to the bound `Client` (experiments are now
  end-to-end Client-only; the `Engine` forms remain for advanced use).

  ```python
  client = shipeasy.Client(user)
  exp = client.get_experiment("checkout_test", default_params={})
  client.log_exposure("checkout_test")   # at the decision point
  client.track("purchase", {"amount": 49})  # on conversion
  ```

  `Client.track(event_name, properties=None)` derives the unit from the bound
  attribute map (`user_id` else `anonymous_id`); `Client.log_exposure(
  experiment_name)` forwards the bound attributes. Both delegate to the
  corresponding `Engine` method.

## 0.8.0 (2026-06-25)

- **BREAKING — `Client` → `Engine` rename + new bound `Client(user)` +
  `configure()`.** The two-part front door, identical across all Shipeasy SDKs:

  ```python
  import shipeasy

  shipeasy.configure(
      api_key="srv_...",
      attributes=lambda u: {"user_id": u.id, "plan": u.plan},
  )

  flag = shipeasy.Client(user).get_flag("new_checkout")
  ```

  - The heavyweight class (owns the api key, HTTP, blob cache, poll timer,
    `init`/`init_once`, `override_*`, `track`, `see`, sticky, private attrs, the
    `for_testing`/`from_snapshot`/`from_file` factories) is **renamed `Client` →
    `Engine`**. Its public surface is otherwise unchanged. `see()`'s
    last-constructed default-client wiring now hooks off `Engine` construction
    (and therefore off `configure()`).
  - New module-level `configure(api_key, *, attributes=None, init=True,
    **engine_opts)` builds **one** `Engine` (first-config-wins), stores it as the
    package-global engine plus the `attributes` transform, and kicks off the
    one-shot fetch fire-and-forget (pass `init=False` to skip, then call
    `engine.init()` yourself for the background poll). `attributes` maps *your*
    user object to the Shipeasy attribute map; default = identity (the user IS
    the attribute map).
  - **`Client` is now the lightweight, user-bound handle.** `Client(user)` reads
    the global engine (raises `RuntimeError` if `configure()` wasn't called),
    runs the `attributes` transform + the existing anon-id merge once at
    construction, and exposes `get_flag(name, default=False)`,
    `get_flag_detail(name)`, `get_config(name, decode=None, default=None)`,
    `get_experiment(name, default_params, decode=None)`, and
    `get_killswitch(name, switch_key=None)` — all with **no user argument**. It
    owns no HTTP/cache/poll; every call forwards to the engine with the bound
    attrs.
  - New `Engine.get_killswitch(name, switch_key=None)` reads the kill switch
    signal from the flags blob (`switch_key` reports a named per-key override).
  - Exports: `Engine`, `Client`, `configure`, `get_global_engine`,
    `reset_global`, `AttributesFn`. The OpenFeature provider now wraps an
    `Engine`.
  - **Migration:** replace `Client(api_key=...)` with `Engine(api_key=...)`
    (and `Client.for_testing()`/`from_snapshot`/`from_file` with `Engine.*`), or
    adopt `configure()` + `Client(user)`.

## 0.7.0 (2026-06-20)

- **SSR bootstrap script-tag helpers.** New `Client.evaluate(user)`
  batch-evaluate (every gate/config/experiment → a `{"flags", "configs",
  "experiments", "killswitches"}` payload) plus `bootstrap_script_tag()` and
  `i18n_script_tag()`, which emit the cross-platform declarative `<script>` tags
  carrying the SSR payload as `data-*` attributes. The static `se-bootstrap.js`
  loader hydrates `window.__SE_BOOTSTRAP` and writes the `__se_anon_id` cookie so
  the browser buckets identically to the server. **No SDK key is embedded** in
  the bootstrap tag.

- **see() structured error reporting.** New `see()` API, mirroring the
  TypeScript SDK's `@shipeasy/sdk` grammar, for reporting handled exceptions
  with their product consequence into the Errors primitive. Available both as an
  instance method (`client.see(e).causes_the("checkout").to("use cached prices")
  .extras({...})`) and as package-level functions (`from shipeasy import see`)
  backed by the last-constructed client. Also `see_violation(name)` for
  non-exception problems and `control_flow_exception(e).because("because …")` to
  mark expected control flow (reports nothing). Dispatch is fire-and-forget to
  `/collect`; `.to(outcome)` is the terminal that sends. Events carry
  `sdk_version` (new), `env`, sanitized `extras` (≤20 keys, 200-char values),
  and are spam-guarded (30s dedup window, 25/process cap). Reporting never
  blocks or throws into caller code, and is a no-op in test/offline mode.

- **OpenFeature provider.** Added `shipeasy.openfeature.ShipeasyProvider`, an
  implementation of the OpenFeature python-server provider contract
  (`openfeature.provider.AbstractProvider`) that wraps a `Client`. Metadata name
  `"shipeasy"`. `resolve_boolean_details` evaluates the gate with a user built
  from the evaluation context (`targeting_key` → `user_id`, attributes → user
  attrs) and maps reasons RULE_MATCH→TARGETING_MATCH, DEFAULT→DEFAULT,
  OFF→DISABLED, OVERRIDE→STATIC, FLAG_NOT_FOUND→ERROR+FLAG_NOT_FOUND,
  CLIENT_NOT_READY→ERROR+PROVIDER_NOT_READY. `resolve_string/integer/float/
  object_details` route to `get_config(key)`: absent → default + DEFAULT,
  type mismatch → default + TYPE_MISMATCH, present → value + TARGETING_MATCH.
  `openfeature-sdk` is an OPTIONAL dependency — install the extra with
  `pip install shipeasy[openfeature]`; importing the base `shipeasy` package
  never requires it.
- **Private attributes.** New `private_attributes` client option (a list of
  attribute keys). Those keys are stripped from every outbound event
  `properties` bag in `track()` before POSTing to `/collect` (LD/Statsig
  `privateAttributes`). Evaluation runs locally, so private attrs still drive
  targeting — they just never leave the process on the telemetry path.
- **Manual exposure (server).** Added `log_exposure(user_or_user_id,
  experiment_name)` — accepts a bare `user_id` string (wrapped as `{"user_id":
  ...}`) or a full user dict. The server never auto-logs; this re-evaluates the
  experiment and, if the user is enrolled, POSTs a single `{type:"exposure",
  experiment, group, user_id, ts}` event to `/collect`. No-op when not enrolled
  or in test mode. Parity with the browser's auto-exposure.
- **Sticky bucketing (server).** Added a `StickyBucketStore` protocol
  (`get(unit) -> {exp: StickyEntry} | None`, `set(unit, exp, entry)`), a
  `StickyEntry = {"g": group, "s": salt8}` shape, an `InMemoryStickyStore`
  implementation, and a `sticky_store` client option (absent ⇒ deterministic).
  In experiment eval, after the holdout and before the allocation gate, a stored
  entry for `(unit, exp)` whose salt prefix still matches skips allocation and
  returns the stored group (so a shrinking allocation keeps an enrolled unit
  in). A fresh pick writes the entry; a salt-prefix mismatch or a vanished
  stored group re-buckets and overwrites. `unit` is the `bucketBy`-resolved
  identifier (`pick_identifier`). Mirrors the TypeScript reference (doc 20 §2).
- **Per-experiment `bucketBy`.** Experiment evaluation now honors an optional
  `bucketBy` attribute (e.g. `company_id`): when set and present on the user it
  becomes the bucketing unit for the holdout, allocation, AND group hashes, so a
  whole org buckets onto one variant together. Absent or unusable ⇒ falls back to
  `user_id`/`anonymous_id`, matching gate rollout. Mirrors the canonical
  `pickIdentifier` in `@shipeasy/core`; locked by the cross-language
  golden-vector fixture.
- **Default values on `get_flag`/`get_config`.** `get_flag(name, user,
  default=False)` returns `default` only when the flag *cannot* be evaluated
  (client not initialized, or the gate isn't in the blob) — never when it
  simply evaluates to False. `get_config(name, decode=None, default=None)`
  returns `default` when the key is absent or `decode` raises. Both additive
  and backward-compatible.
- **Flag evaluation detail.** Added `get_flag_detail(name, user) ->
  FlagDetail(value, reason)` and exported the reason constants
  `CLIENT_NOT_READY`, `FLAG_NOT_FOUND`, `OFF`, `OVERRIDE`, `RULE_MATCH`,
  `DEFAULT`. The reason is computed at the boundary without touching the
  canonical `eval_gate`; the "gate" telemetry beacon fires exactly once and
  never on an override. `get_flag` now delegates to `get_flag_detail`.
- **Change listeners.** Added `on_change(fn) -> unsubscribe` — the callback
  fires (in the poll thread) after a background fetch returns NEW data (a 200,
  not a 304). Listener errors are isolated; never fires in test/offline mode.
- **Offline data source.** Added `Client.from_file(path)` and
  `Client.from_snapshot(flags, experiments)` — a no-network client that runs
  real evaluation against a JSON snapshot (`{"flags": ..., "experiments":
  ...}`). Reuses the test-mode plumbing (telemetry off,
  `init()`/`init_once()`/`track()` no-op); `override_*` setters apply on top.
- **Local-override test utility.** Added `Client.for_testing()` — a no-network,
  immediately-usable client (no api_key, telemetry off, `init()`/`init_once()`/
  `track()` are no-ops). New override setters (also usable on a normal client):
  `override_flag`, `override_config`, `override_experiment`, and
  `clear_overrides`. An override always wins in `get_flag`/`get_config`/
  `get_experiment` (Statsig-style local overrides). See the README "Testing"
  section.

## 0.3.0

- **Anonymous bucketing (`__se_anon_id`).** Added `AnonIdMiddleware` (WSGI) and
  `AnonIdASGIMiddleware` (ASGI) — zero-dependency middleware that mints the
  shared `__se_anon_id` first-party cookie for any request without one and
  exposes it on the request (`environ["shipeasy.anon_id"]`). Gate/experiment
  evaluations now default to the cookie id as `anonymous_id` (via a `ContextVar`,
  so it works under threads and asyncio), so anonymous visitors bucket
  consistently across server renders and the browser with no per-call wiring.
  Implements the cross-SDK contract in `18-identity-bucketing.md`.
- **Eval fix (no-unit gate rule).** A request with no `user_id`/`anonymous_id`
  now resolves a fully-rolled (100%) gate as **on** instead of always off; a
  fractional gate is still off until a stable unit exists. Matches the
  TypeScript reference SDK. Targeting rules are still evaluated first.

## 0.2.0

- Per-evaluation usage telemetry (fire-and-forget, on by default).

## 0.1.0

- Initial release: feature flags, configs, experiments, metric tracking.
