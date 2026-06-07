"""Per-evaluation usage telemetry.

Fires one fire-and-forget HTTP beacon per evaluation so usage is counted by
Cloudflare's native per-path analytics (zero storage on our side). Mirrors the
contract in the TypeScript reference SDK and experiment-platform/15-usage-metering.md.

The path carries sha256(sdk_key) -- never the raw key, so a secret server key
never lands in edge logs -- plus side/env, then feature/resource. A long-lived
Python process can emit reliably (unlike Cloudflare Workers), so a daemon thread
per beacon is fine; the 2s dedup window bounds volume under render/loop storms.
"""
from __future__ import annotations

import hashlib
import threading
import time
import urllib.request
from urllib.parse import quote
from typing import Dict

DEFAULT_TELEMETRY_URL = "https://t.shipeasy.ai"
_FEATURES = frozenset({"gate", "config", "ks", "experiment", "event"})


class Telemetry:
    def __init__(
        self,
        endpoint: str,
        sdk_key: str,
        side: str = "server",
        env: str = "prod",
        disabled: bool = False,
        dedupe_ms: int = 2000,
    ) -> None:
        endpoint = (endpoint or "").rstrip("/")
        self._disabled = disabled or not sdk_key or not endpoint
        self._dedupe_ms = dedupe_ms
        self._last: Dict[str, float] = {}
        self._lock = threading.Lock()
        if self._disabled:
            self._prefix = ""
        else:
            key_hash = hashlib.sha256(sdk_key.encode("utf-8")).hexdigest()
            self._prefix = f"{endpoint}/t/{key_hash}/{side}/{quote(env, safe='')}"

    def emit(self, feature: str, resource: str) -> None:
        """Best-effort usage beacon for one evaluation. Never blocks, never raises."""
        if self._disabled:
            return
        if self._dedupe_ms > 0:
            dedupe_key = f"{feature}/{resource}"
            now = time.monotonic() * 1000.0
            with self._lock:
                last = self._last.get(dedupe_key)
                if last is not None and now - last < self._dedupe_ms:
                    return
                self._last[dedupe_key] = now
        url = f"{self._prefix}/{feature}/{quote(resource, safe='')}"
        threading.Thread(target=_send, args=(url,), daemon=True).start()


def _send(url: str) -> None:
    try:
        req = urllib.request.Request(url, method="GET")
        urllib.request.urlopen(req, timeout=2).close()
    except Exception:  # noqa: BLE001 -- telemetry must never affect the caller
        pass
