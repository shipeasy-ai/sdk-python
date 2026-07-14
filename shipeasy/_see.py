"""see — shipeasy error. Structured error reporting for the server SDK.

Mirrors ``@shipeasy/sdk`` (``packages/ts-sdk/src/see/core.ts``). Every handled
exception documents its product *consequence*, not just its stack:

    from shipeasy import see

    try:
        charge_card(order)
    except Exception as e:
        see(e).causes_the("checkout").to("use the backup processor").extras(
            {"order_id": order.id}
        ).to(...)  # NOTE: in Python `.to()` is the terminal — see below.

Dispatch model (differs from TS, which uses a microtask): ``.to(outcome)`` is
the terminal — it builds the wire event and fire-and-forgets the POST to
``/collect``. ``causes_the()`` and ``extras()`` are chainable setters called
*before* ``.to()``; ``.to()`` also accepts the extras inline as a second arg, so
there is no ordering trap to remember::

    see(e).causes_the("checkout").to("use cached prices")
    see(e).causes_the("checkout").extras({"order_id": oid}).to("use cached prices")
    see(e).causes_the("checkout").to("use cached prices", {"order_id": oid})

``.extras()`` chained AFTER ``.to()`` is ignored with a warning (the report
already went out) — it never raises into the ``except`` block. ``.to()`` returns
the chain, so a stray trailing ``.extras()`` chains harmlessly.

To attach context from anywhere in a request without threading it into the
``except`` block, use the ambient buffer: ``shipeasy.add_extras(order_id=oid)``
merges into EVERY see() report that fires later in the same request. It is scoped
by ``contextvars`` (concurrent requests / async tasks never bleed) and the
WSGI/ASGI/Django middleware clears it at the end of each request.

If you don't know the consequence of an exception, don't catch it.
"""

from __future__ import annotations

import contextvars
import logging
import threading
import time
import traceback
from typing import Any, Callable, Mapping, Optional, Union

from . import _logging as _log

log = logging.getLogger("shipeasy")

# ---- Limits (mirror core.ts; kept in sync with the worker's /collect) ----
SEE_MAX_MESSAGE = 500
SEE_MAX_STACK = 8000
SEE_MAX_SUBJECT = 200
SEE_MAX_EXTRA_VALUE = 200
SEE_MAX_EXTRA_KEYS = 20
SEE_DEDUP_WINDOW_MS = 30_000
SEE_MAX_PER_PROCESS = 25

# Default consequence parts when a chain omits them.
_DEFAULT_SUBJECT = "app"
_DEFAULT_OUTCOME = "hit an error"

# Marker attribute stamped onto an exception by control_flow_exception().
_EXPECTED_ATTR = "_shipeasy_see_expected"


def _truncate(s: str, limit: int) -> str:
    return s if len(s) <= limit else s[:limit]


def sanitize_extras(
    extras: Optional[Mapping[str, Any]],
) -> Optional[dict]:
    """Drop None values, keep only str/finite-number/bool, truncate strings to
    200 chars, cap at 20 keys (insertion order). Returns None if nothing kept.
    """
    if not extras or not isinstance(extras, Mapping):
        return None
    out: dict[str, Any] = {}
    n = 0
    for k, v in extras.items():
        if v is None:
            continue
        if n >= SEE_MAX_EXTRA_KEYS:
            break
        if isinstance(v, bool):
            out[str(k)] = v
        elif isinstance(v, str):
            out[str(k)] = _truncate(v, SEE_MAX_EXTRA_VALUE)
        elif isinstance(v, (int, float)):
            # bool already handled above; reject inf/nan
            if v != v or v in (float("inf"), float("-inf")):
                continue
            out[str(k)] = v
        else:
            continue
        n += 1
    return out or None


class Violation:
    """A non-exception problem. The name is a stable fingerprint key — put
    variable data in ``.extras()``, never in the name.
    """

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = str(name)


def mark_expected(err: Any, because: str, extras: Optional[Mapping[str, Any]] = None) -> None:
    """Best-effort stamp marking an exception as expected control flow."""
    try:
        mark = {"because": str(because)}
        clean = sanitize_extras(extras)
        if clean:
            mark["extras"] = clean
        setattr(err, _EXPECTED_ATTR, mark)
    except Exception:  # noqa: BLE001 — frozen/builtin objects: best effort
        pass


def is_expected(err: Any) -> bool:
    return getattr(err, _EXPECTED_ATTR, None) is not None


# ---- Wire event construction ----

# Dispatch callable: (event_dict) -> None. Bound per client.
Dispatch = Callable[[dict], None]


def build_see_event(
    problem: Any,
    subject: str,
    outcome: str,
    extras: Optional[Mapping[str, Any]],
    *,
    side: str,
    sdk_version: str,
    env: Optional[str],
    kind_override: Optional[str] = None,
) -> dict:
    """Build the ``type:"error"`` event accepted by POST /collect."""
    stack: Optional[str] = None
    if isinstance(problem, Violation):
        error_type = problem.name
        message = problem.name
        kind = kind_override or "violation"
    elif isinstance(problem, BaseException):
        error_type = type(problem).__name__ or "Error"
        message = str(problem) or error_type
        try:
            stack = "".join(
                traceback.format_exception(type(problem), problem, problem.__traceback__)
            ).strip() or None
        except Exception:  # noqa: BLE001
            stack = None
        kind = kind_override or "caught"
    else:
        error_type = "Error"
        message = problem if isinstance(problem, str) else repr(problem)
        kind = kind_override or "caught"

    ev: dict = {
        "type": "error",
        "kind": kind,
        "error_type": _truncate(str(error_type), SEE_MAX_SUBJECT),
        "message": _truncate(str(message), SEE_MAX_MESSAGE),
        "subject": _truncate(str(subject), SEE_MAX_SUBJECT),
        "outcome": _truncate(str(outcome), SEE_MAX_SUBJECT),
        "side": side,
        "sdk_version": sdk_version,
        "ts": int(time.time() * 1000),
    }
    if stack:
        ev["stack"] = _truncate(stack, SEE_MAX_STACK)
    clean = sanitize_extras(extras)
    if clean:
        ev["extras"] = clean
    if env:
        ev["env"] = env
    return ev


# ---- Spam limiter (mirror SeeLimiter) ----


def _top_stack_line(stack: Optional[str]) -> str:
    if not stack:
        return ""
    for line in stack.splitlines():
        s = line.strip()
        if s.startswith("File ") or s.startswith("at ") or "line " in s:
            return s[:200]
    return ""


class SeeLimiter:
    """Per-process spam guard: identical events within 30s collapse to one send;
    a hard cap bounds total sends. Thread-safe. The worker dedupes by
    fingerprint anyway — this only bounds network chatter from a hot loop.
    """

    def __init__(
        self,
        max_per_process: int = SEE_MAX_PER_PROCESS,
        dedup_window_ms: int = SEE_DEDUP_WINDOW_MS,
    ) -> None:
        self._max = max_per_process
        self._window = dedup_window_ms
        self._last: dict[str, int] = {}
        self._sent = 0
        self._lock = threading.Lock()

    def should_send(self, ev: dict) -> bool:
        with self._lock:
            if self._sent >= self._max:
                return False
            key = "|".join(
                [
                    str(ev.get("kind")),
                    str(ev.get("error_type")),
                    str(ev.get("message", ""))[:200],
                    _top_stack_line(ev.get("stack")),
                ]
            )
            now = int(time.time() * 1000)
            prev = self._last.get(key)
            if prev is not None and now - prev < self._window:
                return False
            self._last[key] = now
            self._sent += 1
            return True


# ---- Fluent chains ----


class _SeeChain:
    """Accumulates consequence + extras; ``.to(outcome)`` dispatches once."""

    __slots__ = ("_problem", "_dispatch", "_subject", "_outcome", "_extras", "_done")

    def __init__(self, problem: Any, dispatch: Dispatch) -> None:
        self._problem = problem
        self._dispatch = dispatch
        self._subject: Optional[str] = None
        self._outcome: Optional[str] = None
        self._extras: Optional[dict] = None
        self._done = False

    def causes_the(self, subject: str) -> "_SeeChain":
        self._subject = str(subject)
        return self

    # camelCase alias for cross-SDK muscle memory.
    causesThe = causes_the

    def extras(self, extras: Mapping[str, Any]) -> "_SeeChain":
        """Attach debugging metadata. Chainable — call repeatedly (keys merge,
        later wins) *before* ``.to()``. Called AFTER ``.to()`` it is a no-op with
        a warning: the report already shipped, so there is nothing to amend and,
        crucially, it must not raise into the caller's ``except`` block. Use
        ``.to(outcome, extras)`` or ``shipeasy.add_extras`` for late/scattered
        context instead.
        """
        if self._done:
            _log.warn(
                "see() .extras(...) called after .to(...) is ignored — "
                "pass extras to .to(outcome, extras) or call .extras before .to"
            )
            return self
        if extras:
            self._extras = {**(self._extras or {}), **dict(extras)}
        return self

    def to(self, outcome: str, extras: Optional[Mapping[str, Any]] = None) -> "_SeeChain":
        """Terminal: build the event and fire-and-forget the report. Idempotent.

        ``extras`` may be passed inline here as the trailing form
        ``.to(outcome, {"order_id": oid})`` — merged like a final ``.extras``
        call (folds under any earlier ``.extras``; later wins). Returns self so a
        stray trailing ``.extras`` chains harmlessly.
        """
        if self._done:
            return self
        if extras:
            self._extras = {**(self._extras or {}), **dict(extras)}
        self._done = True
        self._outcome = str(outcome)
        try:
            self._dispatch(
                _BuiltChain(self._problem, self._subject, self._outcome, self._resolved_extras())
            )
        except Exception:  # noqa: BLE001 — reporting must never raise into caller code
            pass
        return self

    def _resolved_extras(self) -> Optional[dict]:
        """The chain's own extras merged OVER the ambient per-request buffer, so a
        chained key of the same name wins over an ambient one. Returns None when
        both are empty. ``sanitize_extras`` stringifies keys at build time.
        """
        ambient = _ambient_extras()
        if not ambient:
            return self._extras
        if not self._extras:
            return dict(ambient)
        out = dict(ambient)
        out.update(self._extras)
        return out


class _BuiltChain:
    """Plain carrier of a finalized chain handed to the client dispatcher."""

    __slots__ = ("problem", "subject", "outcome", "extras")

    def __init__(self, problem: Any, subject: Optional[str], outcome: str, extras: Optional[dict]) -> None:
        self.problem = problem
        self.subject = subject or _DEFAULT_SUBJECT
        self.outcome = outcome or _DEFAULT_OUTCOME
        self.extras = extras


class _ControlFlowChain:
    """``control_flow_exception(e).because("because ...")`` — marks the exception
    expected and reports NOTHING. ``.extras()`` is stored for local debugging
    only (an expected exception is never transmitted).
    """

    __slots__ = ("_err",)

    def __init__(self, err: Any) -> None:
        self._err = err

    def because(self, reason: str) -> "_ControlFlowTail":
        mark_expected(self._err, reason)
        return _ControlFlowTail(self._err, reason)


class _ControlFlowTail:
    __slots__ = ("_err", "_reason")

    def __init__(self, err: Any, reason: str) -> None:
        self._err = err
        self._reason = reason

    def extras(self, extras: Mapping[str, Any]) -> "_ControlFlowTail":
        mark_expected(self._err, self._reason, extras)
        return self


# ---- Ambient per-request extras -------------------------------------------

# A per-request buffer of extras that merge into EVERY see() report firing later
# in the same execution context. Lets a request attach context (order id, route,
# tenant) from anywhere without threading it into the ``except`` block:
# ``shipeasy.add_extras(order_id=oid)`` here, and any subsequent ``see()`` in
# this request carries it.
#
# Backed by a ContextVar (not thread-local), so it scopes correctly under both
# threaded WSGI servers and asyncio/ASGI — concurrent requests / tasks never
# bleed. The WSGI/ASGI/Django middleware clears it at the end of each request;
# outside a request (jobs, scripts) call ``shipeasy.clear_extras`` yourself when
# a logical unit of work ends.
#
# Values are stored raw and sanitized (scalar-only, truncated, 20-key cap,
# private-attribute stripped) at build time, exactly like chained extras.
_ambient: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "shipeasy_see_ambient_extras", default=None
)


def add_ambient_extras(extras: Mapping[str, Any]) -> None:
    """Merge fields into the current context's buffer (string keys, later wins).
    Non-mapping / empty input is ignored. Never raises."""
    try:
        if not extras or not isinstance(extras, Mapping):
            return
        buf = _ambient.get()
        # Copy-on-write so a token reset by the middleware restores cleanly and
        # sibling contexts that inherited the same dict object don't see writes.
        buf = dict(buf) if buf else {}
        for k, v in extras.items():
            buf[str(k)] = v
        _ambient.set(buf)
    except Exception:  # noqa: BLE001 — never raise from context bookkeeping
        pass


def _ambient_extras() -> dict:
    """A snapshot of the current context's buffer, or {} when empty."""
    buf = _ambient.get()
    return dict(buf) if buf else {}


def clear_ambient_extras() -> None:
    """Drop the current context's buffer so extras never leak to the next
    request handled by this thread/task."""
    _ambient.set(None)


# ---- Global default client ----

_default_client: Any = None
_default_lock = threading.Lock()


def set_default_client(client: Any) -> None:
    """Register the client backing the package-level ``see()`` functions.
    Called automatically when a ``Client`` is constructed (last wins)."""
    global _default_client
    with _default_lock:
        _default_client = client


def _resolve_default() -> Any:
    with _default_lock:
        return _default_client


def see(problem: Any) -> _SeeChain:
    """Report a caught exception (or thrown non-exception) via the default
    client. Use ``client.see()`` to target a specific client."""
    client = _resolve_default()
    if client is None:
        _log.warn("see() called before a client was created — error dropped")
        return _SeeChain(problem, lambda _built: None)
    return client.see(problem)


def see_violation(name: str) -> _SeeChain:
    """Report a non-exception problem via the default client."""
    client = _resolve_default()
    if client is None:
        _log.warn("see_violation() called before a client was created — error dropped")
        return _SeeChain(Violation(name), lambda _built: None)
    return client.see_violation(name)


def control_flow_exception(err: Any) -> _ControlFlowChain:
    """Mark an exception as expected control flow (reports nothing). Works
    without a client — it only stamps the exception object."""
    return _ControlFlowChain(err)


# ---- Ambient per-request see() extras (package-level facade) ---------------


def add_extras(extras: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> None:
    """Attach context that merges into every ``see()`` report firing later in
    this request, from anywhere — no need to thread it into the ``except`` block::

        shipeasy.add_extras(order_id=order.id, tenant=tenant.slug)
        # ...later, somewhere else in the same request...
        except Exception as e:
            shipeasy.see(e).causes_the("checkout").to("use cached prices")
            # ^ report carries order_id + tenant automatically

    Scoped by ``contextvars``, so concurrent requests / async tasks never bleed.
    The WSGI/ASGI/Django middleware clears the buffer per request; outside a
    request, call :func:`clear_extras` when a unit of work ends. Accepts a
    mapping and/or keyword args (kwargs win on key collision). Works with no
    client configured (it only writes the buffer); never raises.
    """
    merged: dict = {}
    if extras and isinstance(extras, Mapping):
        merged.update(extras)
    if kwargs:
        merged.update(kwargs)
    add_ambient_extras(merged)


def clear_extras() -> None:
    """Drop the ambient extras buffer for the current request/context."""
    clear_ambient_extras()
