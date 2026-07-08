"""Tiny leveled logger for the SDK's internal diagnostics.

All internal diagnostic logging goes through the helpers here so a single
``log_level`` config option (set from ``Engine.__init__`` via
:func:`set_log_level`) gates every message. Levels, ordered least→most verbose::

    silent < error < warn < info < debug

A message emitted at level ``L`` is shown iff the configured level is ``>= L``
(so the default ``"warn"`` shows ``error`` + ``warn``, mutes ``info`` + ``debug``,
and ``"silent"`` mutes everything). An unknown/invalid configured value is
ignored and the current level is kept.

Logging itself must never raise into the caller — every helper swallows any
exception from the underlying ``logging`` call.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("shipeasy")

# Ordinal per level (higher = more verbose). "silent" mutes everything.
_LEVELS = {
    "silent": 0,
    "error": 1,
    "warn": 2,
    "info": 3,
    "debug": 4,
}

_DEFAULT_LEVEL = "warn"

# Configured verbosity ordinal. Default "warn".
_current = _LEVELS[_DEFAULT_LEVEL]


def set_log_level(level: Any) -> None:
    """Set the SDK's internal log verbosity. Accepts one of
    ``"silent" | "error" | "warn" | "info" | "debug"``. An unknown/invalid
    value is ignored (the current level is kept). Never raises.
    """
    global _current
    try:
        key = str(level).strip().lower()
    except Exception:  # noqa: BLE001 — never raise from logging config
        return
    if key in _LEVELS:
        _current = _LEVELS[key]


def get_log_level() -> str:
    """Return the current level as a string (``"silent"``..``"debug"``)."""
    for name, ordinal in _LEVELS.items():
        if ordinal == _current:
            return name
    return _DEFAULT_LEVEL


def _emit(threshold: int, py_level: int, msg: str, *args: Any) -> None:
    """Emit ``msg`` iff the configured level is >= ``threshold``. Swallows any
    error from the underlying logging call so logging never raises."""
    if _current < threshold:
        return
    try:
        log.log(py_level, msg, *args)
    except Exception:  # noqa: BLE001 — logging must never raise into the caller
        pass


def error(msg: str, *args: Any) -> None:
    _emit(_LEVELS["error"], logging.ERROR, msg, *args)


def warn(msg: str, *args: Any) -> None:
    _emit(_LEVELS["warn"], logging.WARNING, msg, *args)


def info(msg: str, *args: Any) -> None:
    _emit(_LEVELS["info"], logging.INFO, msg, *args)


def debug(msg: str, *args: Any) -> None:
    _emit(_LEVELS["debug"], logging.DEBUG, msg, *args)
