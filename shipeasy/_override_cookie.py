"""Signed DevTools override cookie (``se_ov``) — verifier.

VENDORED copy of the canonical implementation in the shipeasy monorepo
(``packages/core/src/overrides/cookie.ts``); it MUST stay byte-compatible with
it. The cross-impl fixture in ``tests/test_request_overrides.py`` guards drift.

Wire format: ``base64url(JSON payload) + "." + base64url(HMAC-SHA256(Ks, body))``
(no padding), where the session key is
``Ks = HMAC-SHA256(key=Kp, msg="se-ov-sess:v1:<nonce>:<exp>")`` and ``Kp`` is
the project verify key the flags payload serves as ``overrideKey``.

Fails **closed**: any malformation, bad signature, wrong key id or expiry
yields no overrides, and nothing here ever raises to the caller.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional
from urllib.parse import unquote

OVERRIDE_COOKIE_NAME = "se_ov"
OVERRIDE_FORMAT_VERSION = 1
DEV_OVERRIDE_COOKIE_NAME = "se_ov_dev"


def _b64u_decode(s: str) -> bytes:
    pad = "" if len(s) % 4 == 0 else "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def verify_override_cookie(
    cookie_value: str,
    encoded_project_key: str,
    key_id: str,
    now_seconds: Optional[float] = None,
) -> Optional[Dict[str, Dict[str, Any]]]:
    """Verify one ``se_ov`` cookie value against the project key ``Kp``.

    Returns ``{"gates": {...}, "configs": {...}, "exps": {...}}`` or ``None``
    on any failure. ``pid`` is intentionally not checked (``Kp`` binds the
    cookie to a project).
    """
    try:
        project_key = _b64u_decode(encoded_project_key)
        dot = cookie_value.find(".")
        if dot <= 0 or dot != cookie_value.rfind("."):
            return None
        body, sig = cookie_value[:dot], cookie_value[dot + 1 :]
        payload = json.loads(_b64u_decode(body).decode("utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("v") != OVERRIDE_FORMAT_VERSION
            or not isinstance(payload.get("pid"), str)
            or not isinstance(payload.get("keyId"), str)
            or not isinstance(payload.get("nonce"), str)
            or not _is_number(payload.get("exp"))
            or not payload.get("ov")
        ):
            return None
        if payload["keyId"] != key_id:
            return None
        now = time.time() if now_seconds is None else now_seconds
        exp = payload["exp"]
        if exp <= now:
            return None
        exp_str = str(int(exp)) if float(exp).is_integer() else repr(exp)
        session_key = _hmac(project_key, f"se-ov-sess:v1:{payload['nonce']}:{exp_str}")
        expected = _hmac(session_key, body)
        if not hmac.compare_digest(expected, _b64u_decode(sig)):
            return None
        ov = payload["ov"]
        if not isinstance(ov, dict):
            return None
        return {
            "gates": _dict(ov.get("gates")),
            "configs": _dict(ov.get("configs")),
            "exps": _dict(ov.get("exps")),
        }
    except Exception:  # noqa: BLE001 — fail closed, never raise
        return None


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def extract_override_cookie(value: Optional[str]) -> Optional[str]:
    """Pull the raw ``se_ov`` value from a bare cookie value or a full
    ``Cookie:`` header (``a=1; se_ov=...; b=2``), URL-decoding it."""
    if not value:
        return None
    if ";" not in value and "=" not in value:
        return value if "." in value else None
    try:
        for part in value.split(";"):
            eq = part.find("=")
            if eq < 0:
                continue
            if part[:eq].strip() == OVERRIDE_COOKIE_NAME:
                return unquote(part[eq + 1 :].strip())
    except Exception:  # noqa: BLE001
        return None
    return None


def decode_dev_override_cookie(cookie_header: Optional[str]) -> Optional[Dict[str, Dict[str, Any]]]:
    """Decode the UNSIGNED dev-only ``se_ov_dev`` cookie from a ``Cookie:`` header:
    base64url(JSON ``{"gates","configs","exps"}``), no signature, no expiry.
    Malformed -> ``None``; never raises. Callers must only use this when the
    ``dev_overrides`` option is on AND the process is non-production."""
    try:
        if not cookie_header:
            return None
        for part in cookie_header.split(";"):
            eq = part.find("=")
            if eq < 0 or part[:eq].strip() != DEV_OVERRIDE_COOKIE_NAME:
                continue
            raw = unquote(part[eq + 1 :].strip())
            data = json.loads(_b64u_decode(raw).decode("utf-8"))
            if not isinstance(data, dict):
                return None
            return {
                "gates": _dict(data.get("gates")),
                "configs": _dict(data.get("configs")),
                "exps": _dict(data.get("exps")),
            }
    except Exception:  # noqa: BLE001
        return None
    return None
