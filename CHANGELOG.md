# Changelog

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
