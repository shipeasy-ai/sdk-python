"""Single source of truth for the SDK version string.

Kept in sync with ``pyproject.toml``. Imported by ``__init__`` (as
``__version__``) and by the see() reporter (``sdk_version`` on every event).
"""

SDK_VERSION = "0.13.1"
