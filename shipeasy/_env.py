"""Native runtime-environment detection.

Used ONLY to pick the DEFAULT for outbound egress when the caller does not set it
explicitly:

  - is the SDK allowed to make network requests at all (``is_network_enabled``)?
  - is per-evaluation usage telemetry / logging allowed (``disable_telemetry``)?

Both default to ON in production and OFF everywhere else, so a local/dev/CI run of
an app that embeds the SDK never phones home unless it explicitly opts in.

Precedence for the production decision:
  1. A native runtime env var, checked in order: ``SHIPEASY_ENV``, then the
     Python-conventional ``APP_ENV`` / ``ENV`` / ``PYTHON_ENV``. A value of
     ``"production"`` / ``"prod"`` (case-insensitive) ⇒ prod; any other present
     value (``"development"`` / ``"staging"`` / ``"test"`` / …) ⇒ not prod.
  2. When no native env var is set (common on serverless / short-lived jobs),
     fall back to the SDK's own configured ``env`` option, which the caller sets
     and which itself defaults to ``"prod"``. This keeps a real production deploy
     "on" by default while an ``env="dev"`` config stays quiet.

The ``env`` option is always present (it defaults to ``"prod"``), so the
production decision is always inferrable — the SDK never has to make the field
required. Mirrors the TypeScript reference SDK (``src/env.ts``).
"""
from __future__ import annotations

import os
from typing import Optional

# Native runtime env vars, in precedence order. The first one that is set (even
# to an empty-after-strip value counts as unset) decides the native answer.
_NATIVE_ENV_VARS = ("SHIPEASY_ENV", "APP_ENV", "ENV", "PYTHON_ENV")


def _read_native_env() -> Optional[str]:
    """Return the native runtime environment string, lowercased, or ``None`` when
    none of the recognised vars is set (or all are blank)."""
    for name in _NATIVE_ENV_VARS:
        raw = os.environ.get(name)
        if raw is None:
            continue
        v = raw.strip().lower()
        if v:
            return v
    return None


def is_production_env(configured_env: Optional[str] = None) -> bool:
    """True when the host runtime looks like a production deployment.

    ``configured_env`` is the SDK's own ``env`` option (dev/staging/prod); it is
    consulted only when no native runtime env var is set.
    """
    native = _read_native_env()
    if native is not None:
        return native in ("production", "prod")
    return (configured_env or "prod").strip().lower() == "prod"
