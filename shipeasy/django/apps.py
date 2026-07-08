"""``ShipeasyConfig`` — the Django AppConfig that auto-configures the SDK.

Reading a ``SHIPEASY`` dict from Django settings and calling
:func:`shipeasy.configure` in ``ready()`` is the Django-native equivalent of the
Rails railtie: settings drive the one-and-only ``configure()`` call, so the app
owns nothing but its keys.

Add to ``INSTALLED_APPS``::

    INSTALLED_APPS = [..., "shipeasy.django"]

and configure via a ``SHIPEASY`` settings dict::

    SHIPEASY = {
        "SERVER_KEY": os.environ.get("SHIPEASY_SERVER_KEY"),  # required
        "ATTRIBUTES": "myapp.shipeasy.user_attributes",       # dotted path or callable
        "ENV": "prod",
        "POLL": True,                                          # long-running server
    }

``NETWORK_ENABLED`` (master egress switch — pin it to ``not DEBUG`` so the SDK
is quiet outside production),
Supported keys: ``SERVER_KEY`` (required — absent ⇒ no-op + warning),
``ATTRIBUTES`` (dotted import path to a callable, or a callable),
``ENV``, ``DISABLE_TELEMETRY``, ``PRIVATE_ATTRIBUTES``, ``BASE_URL``, and
``POLL`` (default ``False`` — Django is request-scoped under WSGI).
"""

from __future__ import annotations

import warnings
from typing import Any, Callable, Dict, Optional

from django.apps import AppConfig
from django.utils.module_loading import import_string

import shipeasy


def _resolve_attributes(value: Any) -> Optional[Callable[[Any], Dict[str, Any]]]:
    """Resolve the ``ATTRIBUTES`` setting to a callable.

    Accepts a callable directly, or a dotted import path (``"pkg.mod.fn"``)
    resolved via :func:`django.utils.module_loading.import_string`. ``None`` ⇒
    let ``configure()`` use its identity default.
    """
    if value is None:
        return None
    if callable(value):
        return value
    if isinstance(value, str):
        return import_string(value)
    raise TypeError(
        "SHIPEASY['ATTRIBUTES'] must be a callable or a dotted import path "
        f"string, got {type(value).__name__!r}"
    )


def build_configure_kwargs(settings_dict: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Map a ``SHIPEASY`` settings dict to ``shipeasy.configure(**kwargs)``.

    Returns ``None`` when there is no usable ``SERVER_KEY`` (the caller treats
    that as a no-op). Pure + Django-light (only the dotted-path resolver touches
    Django), so it is unit-testable without booting a full Django settings stack.
    """
    cfg = dict(settings_dict or {})
    api_key = cfg.get("SERVER_KEY")
    if not api_key:
        return None

    kwargs: Dict[str, Any] = {"api_key": api_key}

    attrs = _resolve_attributes(cfg.get("ATTRIBUTES"))
    if attrs is not None:
        kwargs["attributes"] = attrs

    # Django is request-scoped under WSGI: default to a one-shot fetch, not the
    # background poll, unless the app explicitly opts in.
    kwargs["poll"] = bool(cfg.get("POLL", False))

    # Pass-through engine options (only when present, so configure() defaults win).
    for key, opt in (
        ("ENV", "env"),
        ("NETWORK_ENABLED", "is_network_enabled"),
        ("DISABLE_TELEMETRY", "disable_telemetry"),
        ("PRIVATE_ATTRIBUTES", "private_attributes"),
        ("BASE_URL", "base_url"),
    ):
        if key in cfg and cfg[key] is not None:
            kwargs[opt] = cfg[key]

    return kwargs


class ShipeasyConfig(AppConfig):
    name = "shipeasy.django"
    label = "shipeasy"
    verbose_name = "Shipeasy"

    def ready(self) -> None:
        from django.conf import settings

        kwargs = build_configure_kwargs(getattr(settings, "SHIPEASY", None))
        if kwargs is None:
            warnings.warn(
                "Shipeasy: no SERVER_KEY found in the SHIPEASY settings dict — "
                "the SDK is not configured. Set SHIPEASY = {'SERVER_KEY': "
                "os.environ['SHIPEASY_SERVER_KEY'], ...} (mint a server key at "
                "https://app.shipeasy.ai). Reads will raise until configured.",
                stacklevel=2,
            )
            return

        shipeasy.configure(**kwargs)
