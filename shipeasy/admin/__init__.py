"""Optional Admin API client for the Shipeasy Python SDK.

This subpackage is **off by default**: the base ``shipeasy`` package never
imports it, and its dependencies (``urllib3``, ``pydantic``, ``python-dateutil``)
are only installed when you opt in::

    pip install "shipeasy[admin]"

It is a raw, generated projection of the Shipeasy Admin OpenAPI spec — use it to
*administer* resources (create gates, start experiments, etc.) from server code.
For flag/config/experiment *evaluation* keep using ``shipeasy.configure()`` +
``shipeasy.Client(user)``; this is a different surface.

    from shipeasy.admin import AdminClient

    admin = AdminClient(api_key=..., project_id=...)
    admin.flags.list_gates()
"""
from __future__ import annotations

try:
    from ._client import AdminClient
except ModuleNotFoundError as exc:  # pragma: no cover - exercised via the extra
    # The generated client needs the `admin` extra's deps. Re-raise with an
    # actionable hint instead of a bare "No module named 'urllib3'".
    raise ModuleNotFoundError(
        "The Shipeasy Admin API client requires the 'admin' extra. "
        'Install it with:  pip install "shipeasy[admin]"'
    ) from exc

__all__ = ["AdminClient"]
