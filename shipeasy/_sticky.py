from __future__ import annotations

from typing import Dict, Optional, Protocol, TypedDict, runtime_checkable


class StickyEntry(TypedDict):
    """One persisted sticky assignment: ``g`` is the group name, ``s`` is the
    8-char salt prefix that keys a reshuffle (a salt change reshuffles)."""

    g: str
    s: str


@runtime_checkable
class StickyBucketStore(Protocol):
    """Pluggable sticky-bucketing store for the server (doc 20 §2). Keyed by the
    bucketing unit; the value is that unit's per-experiment assignments. Absent
    from the client options ⇒ today's deterministic behaviour. Use
    :class:`InMemoryStickyStore` or a cookie-bridge built from request cookies.
    """

    def get(self, unit: str) -> Optional[Dict[str, StickyEntry]]:
        """Return all of ``unit``'s per-experiment assignments, or ``None``."""
        ...

    def set(self, unit: str, exp: str, entry: StickyEntry) -> None:
        """Persist ``entry`` for ``(unit, exp)``."""
        ...


class InMemoryStickyStore:
    """A process-local sticky store (dict-backed). Handy for tests and
    single-process servers. Pass an optional ``seed`` of pre-existing
    assignments (``{unit: {exp: StickyEntry}}``).
    """

    def __init__(
        self, seed: Optional[Dict[str, Dict[str, StickyEntry]]] = None
    ) -> None:
        self._m: Dict[str, Dict[str, StickyEntry]] = (
            {u: dict(exps) for u, exps in seed.items()} if seed else {}
        )

    def get(self, unit: str) -> Optional[Dict[str, StickyEntry]]:
        return self._m.get(unit)

    def set(self, unit: str, exp: str, entry: StickyEntry) -> None:
        cur = self._m.get(unit)
        if cur is None:
            cur = {}
            self._m[unit] = cur
        cur[exp] = entry
