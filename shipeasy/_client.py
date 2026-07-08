from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
import urllib.error
from typing import Any, Callable, Mapping, Optional, Sequence, TypeVar

from ._eval import (
    ExperimentResult,
    Assignment,
    eval_gate,
    classify_experiment,
    merge_params,
    param_defaults_from_schema,
    _enabled,
)
from ._bootstrap import render_bootstrap_tag, render_i18n_tag
from ._sticky import StickyBucketStore, InMemoryStickyStore, StickyEntry
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
from ._env import is_production_env
from ._version import SDK_VERSION
from . import _anon_id
from . import _see
from . import _logging as _log
from ._logging import set_log_level
from ._see import Violation, build_see_event, SeeLimiter
from ._internal_report import report_internal_error, set_internal_report_context

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

_DEFAULT_BASE_URL = "https://api.shipeasy.ai"
_DEFAULT_POLL_INTERVAL = 30


class Engine:
    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        *,
        env: str = "prod",
        is_network_enabled: Optional[bool] = None,
        disable_telemetry: Optional[bool] = None,
        telemetry_url: Optional[str] = None,
        private_attributes: Optional[Sequence[str]] = None,
        sticky_store: Optional[StickyBucketStore] = None,
        log_level: str = "warn",
        disable_internal_error_reporting: bool = False,
    ) -> None:
        # Set the SDK's internal log verbosity first, so any diagnostic emitted
        # during the rest of construction is already gated. An unknown value is
        # ignored (keeps the default "warn"); see _logging.py.
        set_log_level(log_level)
        self._api_key = api_key
        self._base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        # Deployment env, tagged onto see() error events (telemetry already
        # carries it separately).
        self._env = env
        # Environment-derived egress defaults (see _env.py). Both the master
        # network switch and usage telemetry default to ON in production and OFF
        # everywhere else, so a local/dev/CI run of an app embedding the SDK never
        # phones home unless it opts in. An explicit value always overrides.
        prod = is_production_env(env)
        # Master network gate. When off the SDK is fully OFFLINE: no fetch, no
        # track, no exposure, no see(), no telemetry — reads resolve against
        # overrides / in-code defaults. Reuses the test-mode machinery below.
        self._network_enabled = is_network_enabled if is_network_enabled is not None else prod
        offline = not self._network_enabled
        # Per-evaluation usage telemetry: honour an explicit disable_telemetry,
        # else default to prod-on (off outside production). Forced off offline.
        telemetry_disabled = (disable_telemetry if disable_telemetry is not None else not prod) or offline
        # Attribute keys to strip from every outbound event ``properties`` bag
        # before POSTing to /collect (LD/Statsig ``privateAttributes``). The
        # server evaluates locally, so private attrs still drive targeting —
        # they just never leave the process on the telemetry path.
        self._private_attributes = list(private_attributes or [])
        # Pluggable sticky-bucketing store (doc 20 §2). Absent ⇒ deterministic.
        self._sticky_store = sticky_store
        # Per-evaluation usage telemetry. ON by default; pass
        # disable_telemetry=True to opt out. See _telemetry.py.
        self._telemetry = Telemetry(
            endpoint=telemetry_url or DEFAULT_TELEMETRY_URL,
            sdk_key=api_key,
            side="server",
            env=env,
            disabled=telemetry_disabled,
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
        # A disabled master network switch reuses this exact machinery to enforce
        # "fully offline" — init()/track()/exposure/see() become no-ops and the
        # getters read from an empty seeded blob plus any overrides.
        self._test_mode = offline
        self._flag_overrides: dict[str, bool] = {}
        self._config_overrides: dict[str, Any] = {}
        self._experiment_overrides: dict[str, tuple[str, Any]] = {}
        # Change listeners: fired (in the poll thread) after a background fetch
        # returns NEW data (a 200, not a 304). Guarded by _lock. Never fired in
        # test/offline mode (no poll thread runs there).
        self._change_listeners: list[Callable[[], None]] = []
        # Bounded per-process exposure dedup (``uid:exp:group``) so auto-exposure
        # from repeated assign() calls doesn't spam /collect. Cleared past a soft
        # cap. Guarded by _lock.
        self._exposure_seen: set = set()
        # see() structured error reporting. Per-process spam guard; bound here so
        # repeated reports of the same issue collapse to one send.
        self._see_limiter = SeeLimiter()
        # Register as the default engine backing the package-level see() funcs
        # (last constructed wins — the server-SDK analog of TS's shipeasy({key})).
        _see.set_default_client(self)
        # Wire the internal self-monitoring channel: when a last-resort guard
        # swallows one of the SDK's OWN internal errors, it also ships a see
        # event to Shipeasy's own project (baked-in destination, distinct from
        # this consumer's see() path). ON by default; opt out with
        # disable_internal_error_reporting; forced off in test/offline mode.
        set_internal_report_context(
            side="server",
            sdk_version=SDK_VERSION,
            enabled=(not disable_internal_error_reporting) and not offline,
        )
        # When the master network switch is off, seed empty blobs and mark the
        # client initialized so getters resolve immediately against overrides /
        # in-code defaults — no fetch will ever run (init()/init_once() are gated
        # by _test_mode above).
        if offline:
            self._flags_blob = {}
            self._exps_blob = {}
            self._initialized = True

    @classmethod
    def for_testing(cls) -> "Engine":
        """Build a no-network client for tests. Telemetry is disabled,
        ``init()``/``init_once()`` are no-ops (never fetch), ``track()`` is a
        no-op, and no api_key is required. The client is immediately usable:
        getters resolve against an empty blob plus whatever you seed via the
        ``override_*`` setters.
        """
        client = cls(
            api_key="",
            disable_telemetry=True,
            disable_internal_error_reporting=True,
        )
        client._test_mode = True
        client._flags_blob = {}
        client._exps_blob = {}
        client._initialized = True
        return client

    @classmethod
    def from_snapshot(cls, flags: Optional[dict], experiments: Optional[dict]) -> "Engine":
        """Build an offline client from in-memory blobs (no network, ever).

        ``flags`` is the body of ``/sdk/flags`` (``{"gates": ..., "configs":
        ...}``) and ``experiments`` is the body of ``/sdk/experiments``
        (``{"experiments": ..., "universes": ...}``). Reuses the test-mode
        plumbing: telemetry is off, ``init()``/``init_once()``/``track()`` are
        no-ops, and the client is already initialized — but evaluations run the
        *real* eval logic against the snapshot. ``override_*`` setters still
        apply on top.
        """
        client = cls(
            api_key="",
            disable_telemetry=True,
            disable_internal_error_reporting=True,
        )
        client._test_mode = True
        client._flags_blob = dict(flags) if flags else {}
        client._exps_blob = dict(experiments) if experiments else {}
        client._initialized = True
        return client

    @classmethod
    def from_file(cls, path: str) -> "Engine":
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
        """Force the experiment ``name`` to report the unit as enrolled in
        ``group`` with ``params``. A pure override seam (mirrors ts-sdk and the
        other SDKs): it wins over blob evaluation in the override→classify path,
        so it surfaces through ``universe(name).assign()`` **only for an
        experiment that already exists and is running in the loaded blob** — the
        universe's candidate list drives assignment. It does not synthesize an
        experiment or universe into the blob."""
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
                _log.warn("on_change listener failed: %s", e)

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

        Fail-safe: any unexpected internal error is logged and reported as a
        not-ready detail (``value=False``) — this runtime read never raises.
        """
        try:
            return self._get_flag_detail(name, user)
        except Exception as e:  # noqa: BLE001 — runtime reads must never raise
            _log.error("get_flag_detail(%s) failed: %s", name, e)
            report_internal_error("flags.get_detail", e)
            return FlagDetail(value=False, reason=CLIENT_NOT_READY)

    def _get_flag_detail(self, name: str, user: Mapping[str, Any]) -> FlagDetail:
        # 1. Override wins — short-circuit before telemetry (like the override path).
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

        Fail-safe: any unexpected internal error is logged and ``default`` is
        returned — this runtime read never raises.
        """
        try:
            detail = self.get_flag_detail(name, user)
            if detail.reason in (CLIENT_NOT_READY, FLAG_NOT_FOUND):
                return default
            return detail.value
        except Exception as e:  # noqa: BLE001 — runtime reads must never raise
            _log.error("get_flag(%s) failed: %s", name, e)
            report_internal_error("flags.get", e)
            return default

    def get_config(
        self,
        name: str,
        decode: Optional[Callable[[Any], T]] = None,
        default: Optional[T] = None,
    ) -> Optional[T]:
        """Return config ``name`` (optionally ``decode``-d), or ``default``.

        Fail-safe: a ``decode`` failure logs at warn and returns ``default``;
        any other unexpected internal error logs at error and returns
        ``default`` — this runtime read never raises.
        """
        try:
            return self._get_config(name, decode, default)
        except Exception as e:  # noqa: BLE001 — runtime reads must never raise
            _log.error("get_config(%s) failed: %s", name, e)
            report_internal_error("configs.get", e)
            return default

    def _get_config(
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
                _log.warn("get_config(%s) decode failed: %s", name, e)
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
            _log.warn("get_config(%s) decode failed: %s", name, e)
            return default

    def _eval_experiment_standing(
        self, name: str, exp: Mapping[str, Any], user: Mapping[str, Any]
    ):
        """Evaluate one experiment by name for ``user`` — override → full classify
        pipeline (targeting → universe holdout → holdout gate → sticky →
        allocation → group), merging the universe defaults under the assigned
        variant (§B2). Internal: the public surface is
        ``universe(name).assign(user)``. Reused by the SSR ``evaluate()`` bootstrap
        (keyed by experiment name) and by ``assign_universe``. Returns an
        ``ExpStanding``.
        """
        from ._eval import ExpStanding

        with self._lock:
            flags_blob = self._flags_blob
            exps_blob = self._exps_blob
        universe_name = exp.get("universe")
        universe = (
            (exps_blob or {}).get("universes", {}).get(universe_name)
            if universe_name
            else None
        )
        param_defaults = param_defaults_from_schema(
            universe.get("param_schema") if universe else None
        )
        if name in self._experiment_overrides:
            group, params = self._experiment_overrides[name]
            return ExpStanding(
                state="group", group=group, params=merge_params(param_defaults, params)
            )
        if flags_blob is None or exps_blob is None:
            return ExpStanding(state="out")
        if exp.get("status") != "running":
            return ExpStanding(state="out")

        holdout_range = universe.get("holdout_range") if universe else None

        def _eval_gate_fn(gname: str) -> bool:
            gate = (flags_blob or {}).get("gates", {}).get(gname)
            return bool(gate and eval_gate(gate, user))

        return classify_experiment(
            exp,
            user,
            holdout_range,
            param_defaults,
            _eval_gate_fn,
            exp_name=name,
            sticky_store=self._sticky_store,
        )

    def assign_universe(self, universe_name: str, user: Mapping[str, Any]) -> Assignment:
        """Assign ``user`` within ``universe_name``. A universe is a
        mutual-exclusion pool, so a unit lands in **at most one** experiment; the
        returned :class:`Assignment` exposes the variant + resolved params and
        auto-logs a single exposure when enrolled. An un-enrolled unit still
        resolves ``get()`` to the universe defaults. Never throws. This is the
        sole experiment read path (there is no ``get_experiment`` — a caller asks
        a universe, not an experiment).
        """
        try:
            return self._assign_universe(universe_name, _with_anon_id(user))
        except Exception as e:  # noqa: BLE001 — runtime reads must never raise
            _log.error("assign(%s) failed: %s", universe_name, e)
            report_internal_error("experiments.assign", e)
            return Assignment(None, None, {})

    def _assign_universe(self, universe_name: str, user: Mapping[str, Any]) -> Assignment:
        self._telemetry.emit("experiment", universe_name)
        with self._lock:
            exps_blob = self._exps_blob
        universe = (
            (exps_blob or {}).get("universes", {}).get(universe_name)
            if universe_name
            else None
        )
        param_defaults = param_defaults_from_schema(
            universe.get("param_schema") if universe else None
        )

        def _not_enrolled() -> Assignment:
            return Assignment(None, None, param_defaults or {})

        if exps_blob is None:
            return _not_enrolled()

        # Candidate running experiments in this universe. Deterministic order:
        # pool-slice offset asc (slices are disjoint so ≤1 matches under pooling),
        # then name. A universe-held-out or unallocated unit falls through to the
        # defaults-only handle.
        candidates = [
            (n, e)
            for n, e in (exps_blob.get("experiments") or {}).items()
            if e.get("universe") == universe_name and e.get("status") == "running"
        ]
        candidates.sort(key=lambda item: (item[1].get("poolOffsetBp") or 0, item[0]))

        for name, exp in candidates:
            standing = self._eval_experiment_standing(name, exp, user)
            if standing.state == "group":
                self._post_exposure(user, name, standing.group or "control")
                return Assignment(name, standing.group, standing.params or {})
            # "holdout"/"out": try the next candidate — under pooling only one
            # slice can match, so the loop naturally lands on the winner.
        return _not_enrolled()

    def universe(self, name: str) -> "_UniverseHandle":
        """The universe-first experiment read entry point:
        ``engine.universe("checkout").assign(user)``. Returns a reusable handle
        bound to one universe; ``assign(user)`` picks the ≤1 experiment the unit
        is pooled into and auto-logs a single exposure. See ``assign_universe``.
        """
        return _UniverseHandle(self, name)

    def get_killswitch(self, name: str, switch_key: Optional[str] = None) -> bool:
        """Return whether kill switch ``name`` is engaged (the feature is
        killed). In this SDK kill switches ride the flags blob alongside gates
        and are folded into gate evaluation; ``get_killswitch`` reads that same
        signal at the boundary. With ``switch_key`` it reports a named per-key
        override (the dashboard "switches" feature) when present, falling back to
        the kill switch's top-level value otherwise. Returns ``False`` (not
        killed) when the client isn't initialized or the switch is absent.

        Fail-safe: any unexpected internal error is logged and ``False`` is
        returned — this runtime read never raises.
        """
        try:
            with self._lock:
                entry = (self._flags_blob or {}).get("killswitches", {}).get(name)
            if not entry:
                return False
            if switch_key is not None:
                switches = entry.get("switches") or {}
                if switch_key in switches:
                    return bool(_enabled(switches[switch_key]))
            return bool(_enabled(entry.get("value", entry.get("enabled"))))
        except Exception as e:  # noqa: BLE001 — runtime reads must never raise
            _log.error("get_killswitch(%s) failed: %s", name, e)
            report_internal_error("killswitch.get", e)
            return False

    def _strip_private(
        self, properties: Optional[Mapping[str, Any]]
    ) -> Optional[dict]:
        """Drop caller-marked private attributes from an outbound props bag."""
        if not properties:
            return None
        if not self._private_attributes:
            return dict(properties)
        return {
            k: v for k, v in properties.items() if k not in self._private_attributes
        }

    def evaluate(self, user: Mapping[str, Any]) -> dict:
        """Batch-evaluate every loaded gate, config and experiment for ``user``
        into a bootstrap payload (``{flags, configs, experiments, killswitches}``)
        keyed to match the browser SDK's ``window.__SE_BOOTSTRAP`` shape. Local
        overrides win. Killswitches are folded into per-gate evaluation, so the
        standalone ``killswitches`` map is empty for this SDK. No telemetry.
        """
        user = _with_anon_id(user)
        with self._lock:
            flags_blob = self._flags_blob or {}
            exps_blob = self._exps_blob or {}
            flag_ov = dict(self._flag_overrides)
            config_ov = dict(self._config_overrides)

        flags: dict = {}
        for name, gate in (flags_blob.get("gates") or {}).items():
            flags[name] = flag_ov[name] if name in flag_ov else eval_gate(gate, user)

        configs: dict = {}
        for name, entry in (flags_blob.get("configs") or {}).items():
            configs[name] = (
                config_ov[name] if name in config_ov else (entry or {}).get("value")
            )

        # Per-universe param defaults so the client can resolve
        # ``universe(name).get()`` to a default even when the unit is not enrolled
        # anywhere in the universe. Only universes with running experiments listed.
        universes: dict = {}
        experiments: dict = {}
        for name, exp in (exps_blob.get("experiments") or {}).items():
            uni_name = exp.get("universe")
            if uni_name is not None and uni_name not in universes:
                uni = (exps_blob.get("universes") or {}).get(uni_name)
                universes[uni_name] = {
                    "defaults": param_defaults_from_schema(
                        uni.get("param_schema") if uni else None
                    )
                    or {}
                }
            standing = self._eval_experiment_standing(name, exp, user)
            if standing.state == "group":
                experiments[name] = {
                    "inExperiment": True,
                    "group": standing.group,
                    "params": standing.params or {},
                    "universe": uni_name,
                }
            else:
                experiments[name] = {
                    "inExperiment": False,
                    "group": "control",
                    "params": {},
                    "universe": uni_name,
                }

        return {
            "flags": flags,
            "configs": configs,
            "experiments": experiments,
            "killswitches": {},
            "universes": universes,
        }

    def bootstrap_script_tag(
        self,
        user: Mapping[str, Any],
        *,
        anon_id: Optional[str] = None,
        i18n_profile: str = "en:prod",
        base_url: Optional[str] = None,
    ) -> str:
        """Return the cross-platform SSR bootstrap ``<script>`` tag for a request.
        ``se-bootstrap.js`` reads its ``data-*`` attributes and hydrates
        ``window.__SE_BOOTSTRAP`` (and writes the anon cookie). No key embedded.
        """
        return render_bootstrap_tag(
            self.evaluate(user),
            anon_id=anon_id,
            i18n_profile=i18n_profile,
            base_url=base_url,
        )

    def i18n_script_tag(
        self,
        client_key: str,
        profile: str = "en:prod",
        *,
        base_url: Optional[str] = None,
    ) -> str:
        """Return the i18n loader ``<script>`` tag (uses the public client key)."""
        return render_i18n_tag(client_key, profile, base_url=base_url)

    def track(self, user_id: str, event_name: str, properties: Optional[Mapping[str, Any]] = None) -> None:
        """Fire-and-forget a metric event. Fail-safe: any unexpected internal
        error is logged and swallowed — this runtime method never raises."""
        try:
            if self._test_mode:
                return
            safe_props = self._strip_private(properties)
            body = {
                "events": [{
                    "type": "metric",
                    "event_name": event_name,
                    "user_id": str(user_id),
                    "ts": int(time.time() * 1000),
                    **({"properties": safe_props} if safe_props is not None else {}),
                }]
            }
            data = json.dumps(body).encode("utf-8")
            threading.Thread(
                target=self._post_silent,
                args=("/collect", data),
                daemon=True,
            ).start()
        except Exception as e:  # noqa: BLE001 — track must never raise into the caller
            _log.error("track(%s) failed: %s", event_name, e)
            report_internal_error("track", e)

    def _post_exposure(
        self, user: Mapping[str, Any], experiment: str, group: str
    ) -> None:
        """POST a single exposure for an enrolled ``(user, experiment, group)``.
        Deduped per process (bounded set) so repeated ``assign()`` calls in one
        server don't spam ``/collect``. Fire-and-forget; no-op in test mode. This
        is how ``assign_universe`` auto-logs — the browser's auto-exposure parity
        for SSR. Fail-safe: any unexpected internal error is logged and swallowed.
        """
        try:
            if self._test_mode:
                return
            uid = user.get("user_id") or user.get("anonymous_id")
            dedup_key = f"{uid or ''}:{experiment}:{group}"
            with self._lock:
                if dedup_key in self._exposure_seen:
                    return
                if len(self._exposure_seen) > 5000:
                    self._exposure_seen.clear()
                self._exposure_seen.add(dedup_key)
            event: dict = {
                "type": "exposure",
                "experiment": experiment,
                "group": group,
                "ts": int(time.time() * 1000),
            }
            if user.get("user_id") is not None:
                event["user_id"] = user["user_id"]
            if user.get("anonymous_id") is not None:
                event["anonymous_id"] = user["anonymous_id"]
            body = {"events": [event]}
            data = json.dumps(body).encode("utf-8")
            threading.Thread(
                target=self._post_silent,
                args=("/collect", data),
                daemon=True,
            ).start()
        except Exception as e:  # noqa: BLE001 — exposure must never raise
            _log.error("exposure(%s) failed: %s", experiment, e)
            report_internal_error("exposure", e)

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
            _log.warn("track failed: %s", e)

    # ---- see() structured error reporting ----

    def see(self, problem: Any) -> "_see._SeeChain":
        """Report a caught exception (or thrown non-exception). Fire-and-forget;
        never blocks or throws into the request path. Terminate with
        ``.to(outcome)``::

            client.see(e).causes_the("checkout").to("use cached prices")
        """
        return _see._SeeChain(problem, self._dispatch_see)

    def see_violation(self, name: str) -> "_see._SeeChain":
        """Report a non-exception problem. The name is a stable fingerprint key —
        put variable data in ``.extras()``, never the name."""
        return _see._SeeChain(Violation(name), self._dispatch_see)

    # camelCase alias for cross-SDK muscle memory.
    seeViolation = see_violation

    def control_flow_exception(self, err: Any) -> "_see._ControlFlowChain":
        """Mark an exception as expected control flow — reports nothing."""
        return _see._ControlFlowChain(err)

    controlFlowException = control_flow_exception

    def _dispatch_see(self, built: "_see._BuiltChain") -> None:
        """Build the wire event and fire-and-forget POST it to /collect. No-op in
        test mode. Spam-guarded. Never raises into caller code."""
        if self._test_mode:
            return
        try:
            ev = build_see_event(
                built.problem,
                built.subject,
                built.outcome,
                self._strip_private(built.extras),
                side="server",
                sdk_version=SDK_VERSION,
                env=self._env,
            )
            if not self._see_limiter.should_send(ev):
                return
            data = json.dumps({"events": [ev]}).encode("utf-8")
            threading.Thread(
                target=self._post_silent,
                args=("/collect", data),
                daemon=True,
            ).start()
        except Exception as e:  # noqa: BLE001 — reporting must never raise
            _log.warn("see() send failed: %s", e)

    def _start_poll(self) -> None:
        def loop() -> None:
            while not self._stop.wait(self._poll_interval):
                try:
                    if self._fetch_all():
                        # New data (a 200, not a 304) arrived on this poll.
                        self._notify_change()
                except Exception as e:  # noqa: BLE001
                    _log.warn("background poll failed: %s", e)
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


# ---------------------------------------------------------------------------
# Global configure() + the lightweight, user-bound Client.
#
# The two-part front door (mirrors the TS reference in
# packages/ts-sdk/src/server/index.ts):
#
#   import shipeasy
#   shipeasy.configure(api_key="srv_...", attributes=lambda u: {"user_id": u.id})
#   shipeasy.Client(user).get_flag("new_checkout")
#
# ``configure()`` builds ONE Engine (first-config-wins) and stores it as the
# package-global engine, plus the ``attributes`` transform. ``Client(user)`` is
# cheap: it reads that global engine, applies the transform + the existing
# anon-id merge once at construction, and forwards each call with the bound
# attribute map.
# ---------------------------------------------------------------------------

AttributesFn = Callable[[Any], Mapping[str, Any]]


def _identity_attributes(user: Any) -> Mapping[str, Any]:
    """Default transform: the user object IS already the attribute map."""
    return user


_global_engine: Optional[Engine] = None
_global_attributes: AttributesFn = _identity_attributes
_configure_lock = threading.Lock()


def configure(
    api_key: str,
    *,
    attributes: Optional[AttributesFn] = None,
    init: bool = True,
    poll: bool = False,
    **engine_opts: Any,
) -> Engine:
    """Configure Shipeasy: store the api key + the ``attributes`` transform once
    at process start, then read per request with ``shipeasy.Client(user)``.

    First-config-wins: the first call wires everything up; later calls are a
    no-op and return the same handle. Pass any advanced option as a keyword
    (``base_url``, ``env``, ``is_network_enabled``, ``disable_telemetry``,
    ``private_attributes``, ``sticky_store``, ``log_level`` …) — see the
    configuration docs.

    Environment-derived egress defaults: the master network switch
    (``is_network_enabled``) and usage telemetry (``disable_telemetry``) both
    default to ON in production and OFF in every other environment, so the SDK is
    QUIET BY DEFAULT on a dev machine or in CI — it makes no outbound request
    unless it opts in. "Production" is decided by ``SHIPEASY_ENV`` /
    ``APP_ENV`` / ``ENV`` / ``PYTHON_ENV`` (``production``/``prod`` ⇒ prod),
    falling back to the ``env`` option (default ``"prod"``). Pass
    ``is_network_enabled=True`` (or set ``SHIPEASY_ENV=production``) to restore
    outbound requests outside production; ``is_network_enabled=False`` forces the
    SDK fully offline (reads resolve against overrides / in-code defaults).

    ``log_level`` (default ``"warn"``) tunes the SDK's own internal diagnostics —
    one of ``"silent" | "error" | "warn" | "info" | "debug"``. It only gates the
    SDK's log output; the runtime read/track/see methods stay fail-safe and never
    raise regardless of the level.

    ``attributes`` is a function from *your* user object to the Shipeasy
    attribute map (``{"user_id": ..., "anonymous_id": ..., <targeting attrs>}``)
    that every bound ``Client`` evaluation uses. Default = identity (the user
    object is assumed to already be the attribute map).

    Fetch behaviour:

    - default (``init=True``) — a one-shot fetch is kicked off fire-and-forget so
      the first ``Client(user).get_flag(...)`` resolves against real rules. Ideal
      for serverless / short-lived processes.
    - ``poll=True`` — start the **background poll** (initial fetch + periodic
      refresh) for a long-running server, so flags stay fresh without a redeploy.
      No need to touch any lower-level object — configuration owns the lifecycle.

    (For tests use :func:`configure_for_testing`; for an offline snapshot use
    :func:`configure_for_offline` — both are drop-in siblings of this function.)
    """
    global _global_engine, _global_attributes
    with _configure_lock:
        if _global_engine is not None:
            return _global_engine
        engine = Engine(api_key, **engine_opts)
        _global_engine = engine
        _global_attributes = attributes or _identity_attributes
    if poll:
        # Background poll: initial fetch + periodic refresh (daemon thread).
        threading.Thread(target=engine.init, daemon=True).start()
    elif init:
        # Fire-and-forget one-shot fetch — never block configure().
        threading.Thread(target=engine.init_once, daemon=True).start()
    return engine


def _install_global(engine: Engine, attributes: Optional[AttributesFn]) -> Engine:
    """Replace the package-global engine + transform (used by the
    ``configure_for_*`` siblings, which — unlike ``configure`` — replace so a
    test suite can reconfigure between cases)."""
    global _global_engine, _global_attributes
    with _configure_lock:
        _global_engine = engine
        _global_attributes = attributes or _identity_attributes
    return engine


def _apply_overrides(
    engine: Engine,
    flags: Optional[Mapping[str, bool]],
    configs: Optional[Mapping[str, Any]],
    experiments: Optional[Mapping[str, Any]],
) -> None:
    for name, value in (flags or {}).items():
        engine.override_flag(name, value)
    for name, value in (configs or {}).items():
        engine.override_config(name, value)
    for name, spec in (experiments or {}).items():
        # spec is (group, params)
        group, params = spec
        engine.override_experiment(name, group, params)


def configure_for_testing(
    *,
    attributes: Optional[AttributesFn] = None,
    flags: Optional[Mapping[str, bool]] = None,
    configs: Optional[Mapping[str, Any]] = None,
    experiments: Optional[Mapping[str, Any]] = None,
    log_level: str = "warn",
) -> Engine:
    """Configure Shipeasy in **test mode** — a drop-in sibling of
    :func:`configure` with no network, ever (no api key needed).

    Seed the values your code under test should see via the override args, then
    read them through the ordinary ``shipeasy.Client(user)`` — the same call your
    production code uses:

    >>> shipeasy.configure_for_testing(flags={"new_checkout": True})
    >>> client = shipeasy.Client({"user_id": "u_1"})
    >>> client.get_flag("new_checkout")
    True

    Args:
        attributes: same transform as ``configure`` (default identity).
        flags: ``{name: bool}`` forced ``get_flag`` results.
        configs: ``{name: value}`` forced ``get_config`` results.
        experiments: ``{name: (group, params)}`` forced enrolments.
        log_level: SDK internal-diagnostics verbosity (default ``"warn"``); one of
            ``"silent" | "error" | "warn" | "info" | "debug"``.

    Replaces any previously-configured engine, so tests can reconfigure freely.
    """
    set_log_level(log_level)
    engine = Engine.for_testing()
    _apply_overrides(engine, flags, configs, experiments)
    return _install_global(engine, attributes)


def configure_for_offline(
    snapshot: Optional[Mapping[str, Any]] = None,
    path: Optional[str] = None,
    *,
    attributes: Optional[AttributesFn] = None,
    flags: Optional[Mapping[str, bool]] = None,
    configs: Optional[Mapping[str, Any]] = None,
    experiments: Optional[Mapping[str, Any]] = None,
    log_level: str = "warn",
) -> Engine:
    """Configure Shipeasy **offline** — evaluate the *real* rules from an
    in-memory snapshot or a JSON file, with no network. A drop-in sibling of
    :func:`configure` (no api key needed).

    Provide exactly one source:

    - ``snapshot={"flags": <body of /sdk/flags>, "experiments": <body of /sdk/experiments>}``
    - ``path="snapshot.json"`` — a JSON file ``{"flags": ..., "experiments": ...}``

    Optional ``flags`` / ``configs`` / ``experiments`` overrides are layered on
    top (same shapes as :func:`configure_for_testing`). Then read with
    ``shipeasy.Client(user)``. Replaces any previously-configured engine.

    ``log_level`` (default ``"warn"``) tunes the SDK's internal diagnostics.
    """
    set_log_level(log_level)
    if path is not None:
        engine = Engine.from_file(path)
    elif snapshot is not None:
        engine = Engine.from_snapshot(
            snapshot.get("flags"), snapshot.get("experiments")
        )
    else:
        raise ValueError("configure_for_offline requires either snapshot= or path=")
    _apply_overrides(engine, flags, configs, experiments)
    return _install_global(engine, attributes)


def _require_global(fn_name: str) -> Engine:
    engine = _global_engine
    if engine is None:
        raise RuntimeError(
            f"shipeasy.{fn_name}(...) called before shipeasy.configure(api_key=...)"
        )
    return engine


def on_change(fn: Callable[[], None]) -> Callable[[], None]:
    """Register a listener fired after a background poll fetches NEW data.

    Returns an unsubscribe callable. Requires ``configure(poll=True)`` (no poll
    thread runs otherwise). Configuration owns the engine; you never touch it.
    """
    return _require_global("on_change").on_change(fn)


def override_flag(name: str, value: bool) -> None:
    """Force ``get_flag(name)`` → ``value`` on the spot, for the current config.

    A quick, in-test override layered on top of whatever
    :func:`configure_for_testing` / :func:`configure_for_offline` (or
    :func:`configure`) set up — wins over the blob until :func:`clear_overrides`.
    """
    _require_global("override_flag").override_flag(name, value)


def override_config(name: str, value: Any) -> None:
    """Force ``get_config(name)`` → ``value`` on the spot (see :func:`override_flag`)."""
    _require_global("override_config").override_config(name, value)


def override_experiment(name: str, group: str, params: Any) -> None:
    """Force the experiment ``name`` to report enrolment in ``group`` with
    ``params`` on the spot; it surfaces through ``universe(name).assign()`` (see
    :func:`override_flag` and :meth:`Engine.override_experiment`)."""
    _require_global("override_experiment").override_experiment(name, group, params)


def clear_overrides() -> None:
    """Drop every on-the-spot flag/config/experiment override."""
    _require_global("clear_overrides").clear_overrides()


def i18n_script_tag(
    client_key: str,
    profile: str = "en:prod",
    *,
    base_url: Optional[str] = None,
) -> str:
    """Return the i18n loader ``<script>`` tag (public client key) for SSR.

    Delegates to the configured global engine — call ``configure(...)`` first.
    """
    return _require_global("i18n_script_tag").i18n_script_tag(
        client_key, profile, base_url=base_url
    )


def bootstrap_script_tag(
    user: Mapping[str, Any],
    *,
    anon_id: Optional[str] = None,
    i18n_profile: str = "en:prod",
    base_url: Optional[str] = None,
) -> str:
    """Return the SSR bootstrap ``<script>`` tag for a request (no key embedded).

    Delegates to the configured global engine — call ``configure(...)`` first.
    """
    return _require_global("bootstrap_script_tag").bootstrap_script_tag(
        user, anon_id=anon_id, i18n_profile=i18n_profile, base_url=base_url
    )


def get_global_engine() -> Optional[Engine]:
    """Return the engine built by ``configure()`` (or ``None`` if not yet set)."""
    return _global_engine


def reset_global() -> None:
    """Drop the package-global engine + transform. Tests only."""
    global _global_engine, _global_attributes
    with _configure_lock:
        _global_engine = None
        _global_attributes = _identity_attributes


class _UniverseHandle:
    """A reusable handle bound to one universe on an :class:`Engine`. Returned by
    ``engine.universe(name)``; ``assign(user)`` picks the ≤1 experiment the unit
    is pooled into and returns an :class:`Assignment`, auto-logging one exposure
    when enrolled. See ``Engine.assign_universe``.
    """

    __slots__ = ("_engine", "_name")

    def __init__(self, engine: "Engine", name: str) -> None:
        self._engine = engine
        self._name = name

    def assign(self, user: Mapping[str, Any]) -> Assignment:
        return self._engine.assign_universe(self._name, user)


class _BoundUniverseHandle:
    """A reusable handle bound to one universe AND the ``Client``'s pre-bound
    user. Returned by ``Client.universe(name)``; ``assign()`` takes no user arg —
    it forwards the bound attributes. See :class:`Client`.
    """

    __slots__ = ("_engine", "_name", "_attributes")

    def __init__(self, engine: "Engine", name: str, attributes: Mapping[str, Any]) -> None:
        self._engine = engine
        self._name = name
        self._attributes = attributes

    def assign(self) -> Assignment:
        try:
            return self._engine.assign_universe(self._name, self._attributes)
        except Exception as e:  # noqa: BLE001 — runtime reads must never raise
            _log.error("Client.universe(%s).assign() failed: %s", self._name, e)
            report_internal_error("Client.assign", e)
            return Assignment(None, None, {})


class Client:
    """A cheap, user-bound handle over the global engine built by ``configure()``.

    Construct one per user/request: ``shipeasy.Client(user)``. The configured
    ``attributes`` transform runs once here, and the request-scoped anon-id is
    merged in (same rule as the per-call path), so every method takes NO user
    argument — the user is bound. It owns no HTTP connection, cache, or poll
    timer: it delegates every evaluation to the single configured engine.

    Raises ``RuntimeError`` if ``configure()`` has not been called.
    """

    __slots__ = ("_engine", "attributes")

    def __init__(self, user: Any) -> None:
        engine = _global_engine
        if engine is None:
            raise RuntimeError(
                "shipeasy.Client(user) called before shipeasy.configure(api_key=...)"
            )
        self._engine = engine
        # Run the configured transform, then apply the existing anon-id merge
        # exactly as the per-call path does. Bound once at construction.
        self.attributes: Mapping[str, Any] = _with_anon_id(_global_attributes(user))

    def get_flag(self, name: str, default: bool = False) -> bool:
        try:
            return self._engine.get_flag(name, self.attributes, default)
        except Exception as e:  # noqa: BLE001 — runtime reads must never raise
            _log.error("Client.get_flag(%s) failed: %s", name, e)
            report_internal_error("Client.get_flag", e)
            return default

    def get_flag_detail(self, name: str) -> FlagDetail:
        try:
            return self._engine.get_flag_detail(name, self.attributes)
        except Exception as e:  # noqa: BLE001 — runtime reads must never raise
            _log.error("Client.get_flag_detail(%s) failed: %s", name, e)
            report_internal_error("Client.get_flag_detail", e)
            return FlagDetail(value=False, reason=CLIENT_NOT_READY)

    def get_config(
        self,
        name: str,
        decode: Optional[Callable[[Any], T]] = None,
        default: Optional[T] = None,
    ) -> Optional[T]:
        # Configs are not user-scoped; forward straight to the engine.
        try:
            return self._engine.get_config(name, decode, default)
        except Exception as e:  # noqa: BLE001 — runtime reads must never raise
            _log.error("Client.get_config(%s) failed: %s", name, e)
            report_internal_error("Client.get_config", e)
            return default

    def universe(self, name: str) -> "_BoundUniverseHandle":
        """Return a reusable handle bound to universe ``name`` AND this client's
        user. ``universe(name).assign()`` takes no user arg — it picks the ≤1
        experiment the bound unit is pooled into within the universe, auto-logs a
        single exposure when enrolled, and returns an :class:`Assignment`::

            a = client.universe("checkout").assign()
            if a.get("button_color") == "green":
                ...

        A not-enrolled unit still resolves ``a.get(field, fallback)`` to the
        universe default. This is the sole experiment read path (there is no
        ``get_experiment`` — a caller asks a universe, not an experiment).
        """
        return _BoundUniverseHandle(self._engine, name, self.attributes)

    def get_killswitch(self, name: str, switch_key: Optional[str] = None) -> bool:
        try:
            return self._engine.get_killswitch(name, switch_key)
        except Exception as e:  # noqa: BLE001 — runtime reads must never raise
            _log.error("Client.get_killswitch(%s) failed: %s", name, e)
            report_internal_error("Client.get_killswitch", e)
            return False

    def track(
        self, event_name: str, properties: Optional[Mapping[str, Any]] = None
    ) -> None:
        """Record a conversion/metric event for the bound user. The unit is
        derived from the bound attribute map (``user_id`` else ``anonymous_id``),
        so callers never pass a user — the same handle used for
        ``universe(name).assign()`` records the conversion. Delegates to
        ``Engine.track``; no-op in test/offline mode.
        """
        try:
            unit = self.attributes.get("user_id") or self.attributes.get("anonymous_id")
            if unit is None:
                return
            self._engine.track(unit, event_name, properties)
        except Exception as e:  # noqa: BLE001 — track must never raise into the caller
            _log.error("Client.track(%s) failed: %s", event_name, e)
            report_internal_error("Client.track", e)
