"""Internal self-monitoring channel — SDK bugs that are "on our end".

When the SDK swallows one of its OWN internal errors (the last-resort
``try/except`` guard wrapping every public runtime read in ``_client.py`` —
``get_flag`` / ``get_config`` / ``assign`` / ``get_killswitch`` /
``track``, which keep a read from raising into product code
even when an internal invariant is violated), it ALSO ships a structured see
event here — to Shipeasy's OWN project, NOT the consumer's — so the SDK team
can track SDK-internal failures across every app the SDK runs in.

This is deliberately distinct from the customer-facing ``see()`` path
(``Engine._dispatch_see``), which authenticates with the consumer's key and
lands in the consumer's dashboard. Internal errors must never pollute a
customer's Errors tab, and the SDK team must see them centrally — so this
channel has its own baked-in destination + credential.

Guarantees (identical to telemetry/see): fire-and-forget, never blocks, never
raises into product code, deduped/rate-limited. A failed send is swallowed
silently — it must never log (that would risk recursion through the guard).
"""

from __future__ import annotations

import json
import threading
import urllib.request
from typing import Any, Optional

from ._see import build_see_event, SeeLimiter
from ._version import SDK_VERSION

# ---- Baked-in destination ----
#
# The main Shipeasy project (`.shipeasy`). The credential is a PUBLIC client key
# — the same class of credential already embedded verbatim in every browser
# bundle that ships the client SDK, and mirroring how the CLI bakes Shipeasy's
# own public key for setup-bug self-reporting — so baking it into the published
# package is safe. ``/collect`` treats it as a write-only ingest key; it grants
# no read access. The canonical ingest host is api.shipeasy.ai (the SDK default
# base_url), which routes /collect to the edge worker.
INGEST_URL = "https://api.shipeasy.ai/collect"

# Sentinel used until the real key is minted + baked. While ``_INGEST_KEY`` is
# still the placeholder the channel stays fully inert (see
# ``report_internal_error``), so a build that ships before the key is
# provisioned never fires doomed requests. Mint the key with:
#   shipeasy keys create --type client --env prod \
#     --name "SDK internal error self-reporting" --scopes events:write
# then replace the ``_INGEST_KEY`` initializer below with the returned value.
PLACEHOLDER_KEY = "sdk_client_REPLACE_WITH_SHIPEASY_INTERNAL_ERROR_KEY"
_INGEST_KEY = "sdk_client_00bd4608a03e4084922978f9522614d5"

# Stable consequence. The ``label`` (the guard's operation name, e.g.
# "flags.get") is the subject; the outcome is fixed. Both are constant per
# operation — no variable data — so occurrences of the same internal bug fold
# into one issue on our dashboard (fingerprint = error_type + normalized message
# + top stack + subject|outcome). ``sdk`` marks which language SDK reported it.
_OUTCOME = "returned a safe default"
_SDK_ID = "python"

# Module-level context, set once per process from the Engine constructor —
# mirrors how ``set_log_level`` carries the level. ``None`` until configured (a
# report before configure is a no-op — nothing to attribute it to).
_ctx: Optional[dict] = None
_ctx_lock = threading.Lock()

# Bounds network chatter from a hot internal-error loop (30s dedup window + a
# hard per-process cap). The backend dedupes by fingerprint anyway.
_limiter = SeeLimiter()


def _key_configured() -> bool:
    """True once a real key has been baked in (not the placeholder sentinel)."""
    return bool(_INGEST_KEY) and _INGEST_KEY != PLACEHOLDER_KEY


def set_internal_report_context(
    *, side: str, sdk_version: str, enabled: bool = True
) -> None:
    """Wire the self-monitoring channel. Called from the Engine constructor with
    the SDK side + version. ``enabled`` defaults on; it is forced off in test
    mode (no network) and when the caller opts out via
    ``disable_internal_error_reporting``.
    """
    global _ctx
    with _ctx_lock:
        _ctx = {
            "side": side,
            "sdk_version": sdk_version,
            "enabled": enabled is not False,
        }


def report_internal_error(label: str, err: Any) -> None:
    """Report an SDK-internal error to Shipeasy's own project. Called from the
    last-resort guard's ``except`` block. ``label`` is the swallowed operation
    (e.g. "flags.get") and becomes the stable issue subject. Never raises.
    """
    try:
        ctx = _ctx
        if not ctx or not ctx.get("enabled") or not _key_configured():
            return
        ev = build_see_event(
            err,
            label,
            _OUTCOME,
            {"sdk": _SDK_ID},
            side=ctx["side"],
            sdk_version=ctx["sdk_version"],
            env=None,
            kind_override="caught",
        )
        if not _limiter.should_send(ev):
            return
        data = json.dumps({"events": [ev]}).encode("utf-8")
        threading.Thread(
            target=_send, args=(INGEST_URL, _INGEST_KEY, data), daemon=True
        ).start()
    except Exception:  # noqa: BLE001 — self-reporting must never raise into product code
        pass


def _send(url: str, key: str, data: bytes) -> None:
    try:
        req = urllib.request.Request(
            url,
            data=data,
            # text/plain matches the SDK's existing /collect posts; the worker
            # reads the raw body as JSON.
            headers={"X-SDK-Key": key, "Content-Type": "text/plain"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:  # noqa: BLE001 — a network error must never surface
        pass


# ---- Test seams ----

def _reset_internal_report_for_test() -> None:
    """Reset module state (context + rate limiter + key) so a spec starts from a
    clean, inert channel."""
    global _ctx, _limiter, _INGEST_KEY
    with _ctx_lock:
        _ctx = None
    _limiter = SeeLimiter()
    _INGEST_KEY = PLACEHOLDER_KEY


def _set_internal_ingest_key_for_test(key: str) -> None:
    """Stand in a real-looking key so specs can exercise the send path without
    the (deliberately inert) placeholder blocking it."""
    global _INGEST_KEY
    _INGEST_KEY = key
