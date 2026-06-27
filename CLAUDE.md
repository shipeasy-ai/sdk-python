# CLAUDE.md — shipeasy Python SDK

Guidance for AI agents (and humans) working in this repository.

## What this is

`shipeasy` — the **server** SDK for [Shipeasy](https://shipeasy.dev): feature
flags, dynamic configs, kill switches, A/B experiments, metric tracking, `see()`
error reporting, and SSR/i18n helpers. Server-key only; never embed in a browser.
Source under `shipeasy/`, tests under `tests/` (run with `pytest`).

## The documented public surface (this is a contract)

Users are taught exactly **two** things, and the docs must never drift from them:

1. **`configure()`** — and its siblings `configure_for_testing()` /
   `configure_for_offline()` — for setup.
2. **`shipeasy.Client(user)`** — the cheap, user-bound handle for *all* reads
   (`get_flag` / `get_flag_detail` / `get_config` / `get_killswitch` /
   `get_experiment` / `log_exposure` / `track`).

Plus the package-level helpers that let users avoid the heavyweight object:
`override_flag/override_config/override_experiment/clear_overrides`, `on_change`,
`i18n_script_tag`, `bootstrap_script_tag`, and the `see()` family.

**The `Engine` class is an internal detail. Do NOT document it.** It stays public
for advanced/back-compat use, but no page, snippet, skill, or the README should
tell a user to construct or call an `Engine`. New user-facing capability that
today only exists on the `Engine` should get a `configure`-style or package-level
affordance, then be documented through that.

## HARD RULE: change the SDK → update the docs in the SAME change

`docs/` is the published, user-facing source of truth (rendered at
<https://shipeasy-ai.github.io/sdk-python/> and ingested by the Shipeasy CLI/MCP
`docs` tooling and the central docs portal). If you change the SDK's **public API
or behaviour**, you MUST update the docs in the same commit:

- New/changed/removed public function, method, argument, default, or return shape
  → update the relevant `docs/pages/*.md`, the matching `docs/snippets/**`, the
  `docs/skill/SKILL.md`, and the `README.md`.
- New page / snippet / placeholder → also update `docs/manifest.json`.
- See [`docs/CLAUDE.md`](docs/CLAUDE.md) for the docs structure and conventions.

A code change that lands without its doc update is incomplete. When in doubt,
grep `docs/` and `README.md` for the symbol you touched.

## Versioning & release

- Bump the version in **both** `pyproject.toml` and `shipeasy/_version.py`
  (kept in sync — the version is reported on every `see()` event), and add a
  `CHANGELOG.md` entry.
- Publishing is push-to-`main` via the upstream repo's CI (PyPI Trusted
  Publishing) — a version-bumped push to `main` is the release. Do not
  `pip publish` locally.

## Checks before you commit

- `pytest` (fast; the suite is hermetic — no network).
- New public behaviour ships with a test.
- Docs updated per the hard rule above; `docs/manifest.json` stays valid JSON and
  every path it lists exists.
