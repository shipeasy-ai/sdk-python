"""Django integration for the Shipeasy server SDK.

Add ``"shipeasy.django"`` to ``INSTALLED_APPS`` and a ``SHIPEASY`` dict to your
Django settings, and the app's :class:`~shipeasy.django.apps.ShipeasyConfig`
calls :func:`shipeasy.configure` once at boot — the settings-driven equivalent
of the Rails railtie. Add ``"shipeasy.django.middleware.AnonIdMiddleware"`` to
``MIDDLEWARE`` to mint the shared ``__se_anon_id`` cookie for logged-out traffic.

The fastest way to wire all of that up is::

    python manage.py shipeasy_install

which idempotently patches your settings file and (optionally) your ``.env``.

This module imports Django lazily — importing the base ``shipeasy`` package
never pulls Django in. Only :mod:`shipeasy.django.apps` and
:mod:`shipeasy.django.middleware` import ``django``, and they are only loaded
inside a Django app (via ``INSTALLED_APPS`` / ``MIDDLEWARE``).

The Django ``default_app_config`` convention points at the AppConfig so a bare
``"shipeasy.django"`` entry in ``INSTALLED_APPS`` resolves to it.
"""

from __future__ import annotations

# Django >= 3.2 auto-discovers ``apps.ShipeasyConfig`` because it is the only
# AppConfig in this module, so no ``default_app_config`` shim is needed. We avoid
# importing ``apps`` here so that ``import shipeasy.django`` does not require
# Django until Django itself loads the AppConfig.

__all__ = ["ShipeasyConfig", "AnonIdMiddleware"]


def __getattr__(name: str):  # pragma: no cover - thin lazy re-export
    # Lazy re-exports so the names are importable without forcing a Django import
    # at ``import shipeasy.django`` time (these submodules import ``django``).
    if name == "ShipeasyConfig":
        from .apps import ShipeasyConfig

        return ShipeasyConfig
    if name == "AnonIdMiddleware":
        from .middleware import AnonIdMiddleware

        return AnonIdMiddleware
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
