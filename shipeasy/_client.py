from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
import urllib.error
from typing import Any, Callable, Mapping, Optional, TypeVar

from ._eval import ExperimentResult, eval_experiment, eval_gate, _enabled
from ._detail import (
    FlagDetail,
    CLIENT_NOT_READY,
    FLAG_NOT_FOUND,
    OFF,
    OVERRIDE,
    RULE_MATCH,
    DEFAULT,
)
from ._telemetry import Telemetry, DEFAULT_TELEMETRY_URL
from . import _anon_id

T = TypeVar("T")
log = logging.getLogger("shipeasy")


def _with_anon_id(user: Mapping[str, Any]) -> Mapping[str, Any]:
    """Default ``anonymous_id`` to the request's ``__se_anon_id`` (set by the
    middleware) when the caller passed no explicit unit. A caller-supplied
    ``user_id``/``anonymous_id`` always wins; with no middleware this is a no-op.
    """
    if user.get("user_id") or user.get("anonymous_id"):
        return user
    anon = _anon_id.current()
    if not anon:
        return user
    merged = dict(user)
    merged["anonymous_id"] = anon
    return merged

_DEFAULT_BASE_URL = "https://edge.shipeasy.dev"
_DEFAULT_POLL_INTERVAL = 30


class Client:
    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        *,
        env: str = "prod",
        disable_telemetry: bool = False,
        telemetry_url: Optional[str] = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        # Per-evaluation usage telemetry. ON by default; pass
        # disable_telemetry=True to opt out. See _telemetry.py.
        self._telemetry = Telemetry(
            endpoint=telemetry_url or DEFAULT_TELEMETRY_URL,
            sdk_key=api_key,
            side="server",
            env=env,
            disabled=disable_telemetry,
        )
        self._flags_blob: Optional[dict] = None
        self._exps_blob: Optional[dict] = None
        self._flags_etag: Optional[str] = None
        self._exps_etag: Optional[str] = None
        self._poll_interval = _DEFAULT_POLL_INTERVAL
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._initialized = False
        # Local-override / test-mode state. ``_test_mode`` makes init()/track()
        # no-ops so the client never touches the network; the override maps win
        # over the fetched blob in the getters (Statsig-style local overrides).
        self._test_mode = False
        self._flag_overrides: dict[str, bool] = {}
        self._config_overrides: dict[str, Any] = {}
        self._experiment_overrides: dict[str, tuple[str, Any]] = {}
        # Change listeners: fired (in the poll thread) after a background fetch
        # returns NEW data (a 200, not a 304). Guarded by _lock. Never fired in
        # test/offline mode (no poll thread runs there).
        self._change_listeners: list[Callable[[], None]] = []

    @classmethod
    def for_testing(cls) -> "Client":
        """Build a no-network client for tests. Telemetry is disabled,
        ``init()``/``init_once()`` are no-ops (never fetch), ``track()`` is a
        no-op, and no api_key is required. The client is immediately usable:
        getters resolve against an empty blob plus whatever you seed via the
        ``override_*`` setters.
        """
        client = cls(api_key="", disable_telemetry=True)
        client._test_mode = True
        client._flags_blob = {}
        client._exps_blob = {}
        client._initialized = True
        return client

    @classmethod
    def from_snapshot(cls, flags: Optional[dict], experiments: Optional[dict]) -> "Client":
        """Build an offline client from in-memory blobs (no network, ever).

        ``flags`` is the body of ``/sdk/flags`` (``{"gates": ..., "configs":
        ...}``) and ``experiments`` is the body of ``/sdk/experiments``
        (``{"experiments": ..., "universes": ...}``). Reuses the test-mode
        plumbing: telemetry is off, ``init()``/``init_once()``/``track()`` are
        no-ops, and the client is already initialized — but evaluations run the
        *real* eval logic against the snapshot. ``override_*`` setters still
        apply on top.
        """
        client = cls(api_key="", disable_telemetry=True)
        client._test_mode = True
        client._flags_blob = dict(flags) if flags else {}
        client._exps_blob = dict(experiments) if experiments else {}
        client._initialized = True
        return client

    @classmethod
    def from_file(cls, path: str) -> "Client":
        """Build an offline client from a JSON file (no network, ever).

        The file is ``{"flags": <body of /sdk/flags>, "experiments": <body of
        /sdk/experiments>}``. Both blobs are optional. See ``from_snapshot``.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_snapshot(data.get("flags"), data.get("experiments"))

    def override_flag(self, name: str, value: bool) -> None:
        """Force ``get_flag(name)`` to return ``value`` regardless of the blob."""
        self._flag_overrides[name] = value

    def override_config(self, name: str, value: Any) -> None:
        """Force ``get_config(name)`` to return ``value`` regardless of the blob."""
        self._config_overrides[name] = value

    def override_experiment(self, name: str, group: str, params: Any) -> None:
        """Force ``get_experiment(name)`` to report the caller as enrolled in
        ``group`` with ``params``, regardless of the blob."""
        self._experiment_overrides[name] = (group, params)

    def clear_overrides(self) -> None:
        """Drop every flag/config/experiment override."""
        self._flag_overrides.clear()
        self._config_overrides.clear()
        self._experiment_overrides.clear()

    def on_change(self, fn: Callable[[], None]) -> Callable[[], None]:
        """Register a listener fired after a background poll fetches NEW data
        (a 200, not a 304). Returns an unsubscribe callable. Listeners never
        fire in test/offline mode (no poll thread runs). Each listener is
        called in a try/except so one failing listener can't break the others.
        """
        with self._lock:
            self._change_listeners.append(fn)

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._change_listeners.remove(fn)
                except ValueError:
                    pass

        return unsubscribe

    def _notify_change(self) -> None:
        with self._lock:
            listeners = list(self._change_listeners)
        for fn in listeners:
            try:
                fn()
            except Exception as e:  # noqa: BLE001 -- a listener must not break polling
                log.warning("on_change listener failed: %s", e)

    def init(self) -> None:
        if self._test_mode:
            return
        self._fetch_all()
        self._initialized = True
        self._start_poll()

    def init_once(self) -> None:
        if self._test_mode or self._initialized:
            return
        self._fetch_all()
        self._initialized = True

    def destroy(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None

    def get_flag_detail(self, name: str, user: Mapping[str, Any]) -> FlagDetail:
        """Evaluate ``name`` and report both the value and *why* it resolved
        that way. The reason is computed at the boundary without touching
        ``eval_gate``. The "gate" telemetry beacon is emitted exactly once here
        (steps 2-5) and never on an override.
        """
        # 1. Override wins — short-circuit before telemetry, like get_experiment.
        if name in self._flag_overrides:
            return FlagDetail(value=self._flag_overrides[name], reason=OVERRIDE)

        self._telemetry.emit("gate", name)

        # 2. Not initialized — no blob to evaluate against.
        if not self._initialized:
            return FlagDetail(value=False, reason=CLIENT_NOT_READY)

        with self._lock:
            gate = (self._flags_blob or {}).get("gates", {}).get(name)

        # 3. Gate absent from the blob.
        if not gate:
            return FlagDetail(value=False, reason=FLAG_NOT_FOUND)

        # 4. Gate present but disabled (same predicate eval_gate uses).
        if not _enabled(gate.get("enabled")):
            return FlagDetail(value=False, reason=OFF)

        # 5. Evaluate (targeting + rollout).
        result = eval_gate(gate, _with_anon_id(user))
        return FlagDetail(value=result, reason=RULE_MATCH if result else DEFAULT)

    def get_flag(
        self, name: str, user: Mapping[str, Any], default: bool = False
    ) -> bool:
        """Return the flag's boolean value. ``default`` is returned only when
        the flag CANNOT be evaluated — the client isn't initialized or the gate
        isn't in the blob — never when it simply evaluates to False.
        """
        detail = self.get_flag_detail(name, user)
        if detail.reason in (CLIENT_NOT_READY, FLAG_NOT_FOUND):
            return default
        return detail.value

    def get_config(
        self,
        name: str,
        decode: Optional[Callable[[Any], T]] = None,
        default: Optional[T] = None,
    ) -> Optional[T]:
        if name in self._config_overrides:
            value = self._config_overrides[name]
            if decode is None:
                return value
            try:
                return decode(value)
            except Exception as e:  # noqa: BLE001
                log.warning("get_config(%s) decode failed: %s", name, e)
                return default
        self._telemetry.emit("config", name)
        with self._lock:
            entry = (self._flags_blob or {}).get("configs", {}).get(name)
        if not entry:
            return default
        value = entry.get("value")
        if decode is None:
            return value
        try:
            return decode(value)
        except Exception as e:  # noqa: BLE001
            log.warning("get_config(%s) decode failed: %s", name, e)
            return default

    def get_experiment(
        self,
        name: str,
        user: Mapping[str, Any],
        default_params: T,
        decode: Optional[Callable[[Any], T]] = None,
    ) -> ExperimentResult:
        if name in self._experiment_overrides:
            group, params = self._experiment_overrides[name]
            return ExperimentResult(in_experiment=True, group=group, params=params)
        self._telemetry.emit("experiment", name)
        with self._lock:
            flags_blob = self._flags_blob
            exps_blob = self._exps_blob
        exp = (exps_blob or {}).get("experiments", {}).get(name)
        result = eval_experiment(exp, flags_blob, exps_blob, _with_anon_id(user))
        if result.params is None:
            result.params = default_params
        if result.in_experiment and decode is not None:
            try:
                result.params = decode(result.params)
            except Exception as e:  # noqa: BLE001
                log.warning("get_experiment(%s) decode failed: %s", name, e)
                return ExperimentResult(False, "control", default_params)
        return result

    def track(self, user_id: str, event_name: str, properties: Optional[Mapping[str, Any]] = None) -> None:
        if self._test_mode:
            return
        body = {
            "events": [{
                "type": "metric",
                "event_name": event_name,
                "user_id": str(user_id),
                "ts": int(time.time() * 1000),
                **({"properties": dict(properties)} if properties else {}),
            }]
        }
        data = json.dumps(body).encode("utf-8")
        threading.Thread(
            target=self._post_silent,
            args=("/collect", data),
            daemon=True,
        ).start()

    def _post_silent(self, path: str, data: bytes) -> None:
        try:
            req = urllib.request.Request(
                f"{self._base_url}{path}",
                data=data,
                headers={"X-SDK-Key": self._api_key, "Content-Type": "text/plain"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10).read()
        except Exception as e:  # noqa: BLE001
            log.warning("track failed: %s", e)

    def _start_poll(self) -> None:
        def loop() -> None:
            while not self._stop.wait(self._poll_interval):
                try:
                    if self._fetch_all():
                        # New data (a 200, not a 304) arrived on this poll.
                        self._notify_change()
                except Exception as e:  # noqa: BLE001
                    log.warning("background poll failed: %s", e)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def _fetch_all(self) -> bool:
        """Fetch both blobs. Returns True if either returned NEW data (200)."""
        interval, flags_changed = self._fetch_flags()
        exps_changed = self._fetch_exps()
        if interval and interval != self._poll_interval:
            self._poll_interval = interval
        return flags_changed or exps_changed

    def _fetch_flags(self) -> tuple[Optional[int], bool]:
        status, headers, body = self._http_get("/sdk/flags", self._flags_etag)
        interval_str = headers.get("X-Poll-Interval") or headers.get("x-poll-interval")
        interval = int(interval_str) if interval_str else None
        if status == 304:
            return interval, False
        if status != 200:
            raise RuntimeError(f"GET /sdk/flags returned {status}")
        with self._lock:
            etag = headers.get("ETag") or headers.get("etag")
            if etag:
                self._flags_etag = etag
            self._flags_blob = json.loads(body)
        return interval, True

    def _fetch_exps(self) -> bool:
        status, headers, body = self._http_get("/sdk/experiments", self._exps_etag)
        if status == 304:
            return False
        if status != 200:
            raise RuntimeError(f"GET /sdk/experiments returned {status}")
        with self._lock:
            etag = headers.get("ETag") or headers.get("etag")
            if etag:
                self._exps_etag = etag
            self._exps_blob = json.loads(body)
        return True

    def _http_get(self, path: str, etag: Optional[str]) -> tuple[int, Mapping[str, str], bytes]:
        headers = {"X-SDK-Key": self._api_key}
        if etag:
            headers["If-None-Match"] = etag
        req = urllib.request.Request(f"{self._base_url}{path}", headers=headers, method="GET")
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers or {}), e.read() if e.fp else b""
