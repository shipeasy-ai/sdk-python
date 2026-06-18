from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
import urllib.error
from typing import Any, Callable, Mapping, Optional, TypeVar

from ._eval import ExperimentResult, eval_experiment, eval_gate
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

    def get_flag(self, name: str, user: Mapping[str, Any]) -> bool:
        if name in self._flag_overrides:
            return self._flag_overrides[name]
        self._telemetry.emit("gate", name)
        with self._lock:
            gate = (self._flags_blob or {}).get("gates", {}).get(name)
        if not gate:
            return False
        return eval_gate(gate, _with_anon_id(user))

    def get_config(
        self, name: str, decode: Optional[Callable[[Any], T]] = None
    ) -> Optional[T]:
        if name in self._config_overrides:
            value = self._config_overrides[name]
            if decode is None:
                return value
            try:
                return decode(value)
            except Exception as e:  # noqa: BLE001
                log.warning("get_config(%s) decode failed: %s", name, e)
                return None
        self._telemetry.emit("config", name)
        with self._lock:
            entry = (self._flags_blob or {}).get("configs", {}).get(name)
        if not entry:
            return None
        value = entry.get("value")
        if decode is None:
            return value
        try:
            return decode(value)
        except Exception as e:  # noqa: BLE001
            log.warning("get_config(%s) decode failed: %s", name, e)
            return None

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
                    self._fetch_all()
                except Exception as e:  # noqa: BLE001
                    log.warning("background poll failed: %s", e)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def _fetch_all(self) -> None:
        interval = self._fetch_flags()
        self._fetch_exps()
        if interval and interval != self._poll_interval:
            self._poll_interval = interval

    def _fetch_flags(self) -> Optional[int]:
        status, headers, body = self._http_get("/sdk/flags", self._flags_etag)
        interval_str = headers.get("X-Poll-Interval") or headers.get("x-poll-interval")
        interval = int(interval_str) if interval_str else None
        if status == 304:
            return interval
        if status != 200:
            raise RuntimeError(f"GET /sdk/flags returned {status}")
        with self._lock:
            etag = headers.get("ETag") or headers.get("etag")
            if etag:
                self._flags_etag = etag
            self._flags_blob = json.loads(body)
        return interval

    def _fetch_exps(self) -> None:
        status, headers, body = self._http_get("/sdk/experiments", self._exps_etag)
        if status == 304:
            return
        if status != 200:
            raise RuntimeError(f"GET /sdk/experiments returned {status}")
        with self._lock:
            etag = headers.get("ETag") or headers.get("etag")
            if etag:
                self._exps_etag = etag
            self._exps_blob = json.loads(body)

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
