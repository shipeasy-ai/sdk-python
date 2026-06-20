# Changelog

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
