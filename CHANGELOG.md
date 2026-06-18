# Changelog

## Unreleased

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
