"""SSR bootstrap script-tag rendering.

Cross-platform bootstrap: the server emits declarative ``<script>`` tags whose
``data-*`` attributes carry the request's evaluated flags/configs/experiments.
The static ``se-bootstrap.js`` loader reads them and hydrates
``window.__SE_BOOTSTRAP`` (and writes the anon cookie); the i18n loader installs
translations. No SDK key is ever embedded in the bootstrap tag.
"""

from __future__ import annotations

import html
import json
from typing import Any, Mapping, Optional

_DEFAULT_CDN_BASE = "https://cdn.shipeasy.ai"


def _attr(name: str, value: str) -> str:
    return f'{name}="{html.escape(value, quote=True)}"'


def _cdn_base(override: Optional[str]) -> str:
    return (override or _DEFAULT_CDN_BASE).rstrip("/")


def _identity_attrs(identity: Optional[Mapping[str, Any]]) -> Optional[str]:
    """Serialize the server-identified user's traits for the ``data-user``
    attribute — everything except ``anonymous_id`` (which rides ``data-anon-id``).
    Returns ``None`` for an anonymous request (no identified traits), so the tag
    carries no PII when there is no identity to carry."""
    if not identity:
        return None
    traits = {k: v for k, v in identity.items() if k != "anonymous_id" and v is not None}
    if not traits:
        return None
    return json.dumps(traits)


def render_bootstrap_tag(
    payload: Mapping[str, Any],
    *,
    anon_id: Optional[str] = None,
    identity: Optional[Mapping[str, Any]] = None,
    i18n_profile: str = "en:prod",
    base_url: Optional[str] = None,
) -> str:
    """Render the ``se-bootstrap.js`` tag from an evaluated bootstrap payload.

    When ``identity`` carries a server-identified user, its traits ride the tag
    as ``data-user`` so the browser SDK **adopts** the server's identity on first
    paint (no anon→identified flip) and a later ``identify()`` reconciles
    idempotently. Anonymous requests emit no ``data-user``."""
    base = _cdn_base(base_url)
    attrs = [
        "data-se-bootstrap",
        _attr("data-flags", json.dumps(payload.get("flags", {}))),
        _attr("data-configs", json.dumps(payload.get("configs", {}))),
        _attr("data-experiments", json.dumps(payload.get("experiments", {}))),
        _attr("data-killswitches", json.dumps(payload.get("killswitches", {}))),
        _attr("data-i18n-profile", i18n_profile or "en:prod"),
        _attr("data-api-url", base),
    ]
    if anon_id:
        attrs.append(_attr("data-anon-id", anon_id))
    data_user = _identity_attrs(identity)
    if data_user is not None:
        attrs.append(_attr("data-user", data_user))
    src = html.escape(f"{base}/sdk/bootstrap.js", quote=True)
    return f'<script src="{src}" ' + " ".join(attrs) + "></script>"


def render_i18n_tag(
    client_key: str,
    profile: str = "en:prod",
    *,
    base_url: Optional[str] = None,
) -> str:
    """Render the i18n loader tag. The loader fetches translations for the
    profile using the PUBLIC client key (safe to embed in HTML)."""
    base = _cdn_base(base_url)
    src = html.escape(f"{base}/sdk/i18n/loader.js", quote=True)
    return (
        f'<script src="{src}" '
        + _attr("data-key", client_key)
        + " "
        + _attr("data-profile", profile or "en:prod")
        + "></script>"
    )
