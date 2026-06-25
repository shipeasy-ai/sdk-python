"""Flag evaluation detail — the value plus *why* it resolved that way.

The reason is computed at the SDK boundary (in ``Engine.get_flag_detail``)
without touching the canonical ``eval_gate`` logic, so it stays a pure,
additive layer over evaluation. Mirrors the ``reason`` contract in the
TypeScript reference SDK.
"""
from __future__ import annotations

from dataclasses import dataclass

# Reason constants. Exported from the package top-level.
CLIENT_NOT_READY = "CLIENT_NOT_READY"  # init()/init_once() not run yet
FLAG_NOT_FOUND = "FLAG_NOT_FOUND"      # no gate by that name in the blob
OFF = "OFF"                            # gate exists but is disabled
OVERRIDE = "OVERRIDE"                  # a local override forced the value
RULE_MATCH = "RULE_MATCH"              # evaluated on (targeting + rollout)
DEFAULT = "DEFAULT"                    # evaluated off (fell through)


@dataclass(frozen=True)
class FlagDetail:
    """The resolved flag ``value`` plus the ``reason`` it resolved that way.

    ``reason`` is one of the module-level constants
    (``CLIENT_NOT_READY``/``FLAG_NOT_FOUND``/``OFF``/``OVERRIDE``/
    ``RULE_MATCH``/``DEFAULT``).
    """

    value: bool
    reason: str
