from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional
import re

from ._hash import murmur3
from ._sticky import StickyBucketStore


@dataclass
class ExperimentResult:
    in_experiment: bool
    group: str
    params: Optional[Any]


def _enabled(v: Any) -> bool:
    return v == 1 or v is True


def _to_num(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    return None


def _user_id(user: Mapping[str, Any]) -> Optional[str]:
    uid = user.get("user_id") or user.get("anonymous_id")
    return str(uid) if uid else None


def pick_identifier(user: Mapping[str, Any], bucket_by: Optional[str]) -> Optional[str]:
    """Resolve the bucketing unit for a caller. With ``bucket_by`` set (e.g.
    ``company_id``), hash on that attribute so a whole org buckets together;
    otherwise fall back to ``user_id`` then ``anonymous_id``. When ``bucket_by``
    is named but absent (or not a usable value) on the user, also falls back —
    and if nothing resolves, returns ``None`` (the caller then applies the
    missing-unit rule). Mirrors the canonical ``pickIdentifier`` in
    ``packages/core/src/eval/gate.ts`` so gate rollout and experiment
    holdout/allocation/group stay in sync.
    """
    if bucket_by:
        v = user.get(bucket_by)
        if isinstance(v, str) and len(v) > 0:
            return v
        # bool is a subclass of int; match JS where only number → String(n).
        if isinstance(v, bool):
            pass
        elif isinstance(v, int):
            return str(v)
        elif isinstance(v, float):
            # JS String(number): integral floats render without a fraction.
            return str(int(v)) if v.is_integer() else repr(v)
    return _user_id(user)


def match_rule(rule: Mapping[str, Any], user: Mapping[str, Any]) -> bool:
    attr = rule.get("attr")
    op = rule.get("op")
    value = rule.get("value")
    actual = user.get(attr) if attr else None

    if op == "eq":
        return actual == value
    if op == "neq":
        return actual != value
    if op == "in":
        return actual in (value or [])
    if op == "not_in":
        return actual not in (value or [])
    if op == "contains":
        if isinstance(actual, str) and isinstance(value, str):
            return value in actual
        if isinstance(actual, list):
            return value in actual
        return False
    if op == "regex":
        if isinstance(actual, str) and isinstance(value, str):
            try:
                return re.search(value, actual) is not None
            except re.error:
                return False
        return False
    if op in ("gt", "gte", "lt", "lte"):
        a = _to_num(actual)
        b = _to_num(value)
        if a is None or b is None:
            return False
        if op == "gt":
            return a > b
        if op == "gte":
            return a >= b
        if op == "lt":
            return a < b
        return a <= b
    return False


def eval_gate(gate: Mapping[str, Any], user: Mapping[str, Any]) -> bool:
    if _enabled(gate.get("killswitch")):
        return False
    if not _enabled(gate.get("enabled")):
        return False
    for rule in gate.get("rules") or []:
        if not match_rule(rule, user):
            return False
    uid = _user_id(user)
    if not uid:
        # No unit id (an unidentified request before any anon id is minted): a
        # fully-rolled gate is on for everyone, so it can be answered without
        # bucketing; a fractional rollout genuinely needs a stable unit, so deny
        # until one exists. Rules above are still checked, so targeting wins.
        # See experiment-platform/18-identity-bucketing.md.
        return (gate.get("rolloutPct") or 0) >= 10000
    salt = gate.get("salt") or ""
    return murmur3(f"{salt}:{uid}") % 10000 < (gate.get("rolloutPct") or 0)


# ---- Universe assignment (mutual-exclusion pool eval) ----


def param_defaults_from_schema(
    schema: Optional[Any],
) -> Optional[Dict[str, Any]]:
    """Flatten a universe param schema to a plain ``name → default`` map — the
    defaults ``assign()`` layers under a variant's override map (§B2). Returns
    ``None`` for a null/empty schema so the merge short-circuits. Mirrors
    ``@shipeasy/core``.
    """
    if not schema:
        return None
    out: Dict[str, Any] = {}
    for p in schema:
        out[p.get("name")] = p.get("default")
    return out


def merge_params(
    param_defaults: Optional[Mapping[str, Any]],
    group_params: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """``universeDefaults ⊕ variantOverride`` — a variant inherits every universe
    default it doesn't explicitly override (§B2)."""
    merged: Dict[str, Any] = dict(param_defaults) if param_defaults else {}
    if group_params:
        merged.update(group_params)
    return merged


@dataclass
class ExpStanding:
    """A unit's standing in one experiment: an assigned ``group`` (with merged
    params), ``holdout`` (universe carve-out or holdout gate — never assigned),
    or ``out``."""

    state: str  # "group" | "holdout" | "out"
    group: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


_OUT = ExpStanding(state="out")
_HOLDOUT = ExpStanding(state="holdout")


def _resolve_forced_group(
    exp: Mapping[str, Any], uid: str, eval_gate_fn
) -> Optional[str]:
    """Resolve a forced override group for ``uid`` (spec step 1): ID overrides
    (tier 1) beat cohort/GK overrides (tier 2); within cohort overrides the first
    (pre-sorted by priority) gate that passes wins. Returns the forced group name
    or None. The caller applies eligibility + group-existence (forced-but-gated).
    Mirrors ``@shipeasy/core`` ``resolveForcedGroup``.
    """
    id_overrides = exp.get("idOverrides")
    if id_overrides:
        by_id = id_overrides.get(uid)
        if by_id:
            return by_id
    cohort_overrides = exp.get("cohortOverrides")
    if cohort_overrides:
        for co in cohort_overrides:
            if eval_gate_fn(co.get("gate")):
                return co.get("group")
    return None


def classify_experiment(
    exp: Mapping[str, Any],
    user: Mapping[str, Any],
    holdout_range: Optional[Any],
    param_defaults: Optional[Mapping[str, Any]],
    eval_gate_fn,
    *,
    exp_name: Optional[str] = None,
    sticky_store: Optional[StickyBucketStore] = None,
) -> ExpStanding:
    """Targeting → universe holdout → holdout gate → sticky → allocation (pooled
    or legacy) → weighted group split. The single local mirror of
    ``@shipeasy/core``'s ``classifyExperiment`` — keep the two in sync (see
    experiment-platform/04). ``eval_gate_fn`` is a gate-name → bool lookup over
    the flags blob so the two gate checks reuse the SDK's real gate evaluation.
    """
    groups = exp.get("groups") or []

    def _as_group(g: Mapping[str, Any]) -> ExpStanding:
        return ExpStanding(
            state="group",
            group=g.get("name", "control"),
            params=merge_params(param_defaults, g.get("params")),
        )

    targeting_gate = exp.get("targetingGate")
    if targeting_gate and not eval_gate_fn(targeting_gate):
        return _OUT

    uid = pick_identifier(user, exp.get("bucketBy"))
    if not uid:
        return _OUT

    # One segment in the universe's shared ``[0, 10000)`` hash space. The holdout
    # carve-out AND every experiment's pool slice are disjoint ranges of THIS
    # segment — that's what makes "held out / taken / free" a real partition.
    universe_seg = murmur3(f"{exp.get('universe')}:{uid}") % 10000

    if holdout_range:
        lo, hi = holdout_range[0], holdout_range[1]
        if lo <= universe_seg <= hi:
            return _HOLDOUT

    holdout_gate = exp.get("holdoutGate")
    if holdout_gate and eval_gate_fn(holdout_gate):
        return _HOLDOUT

    salt = exp.get("salt") or ""
    salt8 = salt[:8]

    # Durable overrides (spec step 1, forced-but-gated). Reached only after the
    # unit passes targeting and is not held out, so an override may now pin the
    # group — bypassing allocation + the weighted pick but NOT the gates above. ID
    # overrides (tier 1) beat cohort/GK overrides (tier 2); a forced group that no
    # longer exists falls through to normal allocation. No-op when unconfigured, so
    # v1/v2 stay byte-identical. Mirrors @shipeasy/core ``classifyExperiment``.
    forced = _resolve_forced_group(exp, uid, eval_gate_fn)
    if forced:
        for g in groups:
            if g.get("name") == forced:
                if sticky_store is not None and exp_name is not None:
                    sticky_store.set(uid, exp_name, {"g": forced, "s": salt8})
                return _as_group(g)

    # Sticky short-circuit (doc 20 §2): an enrolled unit whose stored salt prefix
    # still matches skips the allocation gate (so a shrinking allocation keeps it
    # in) and returns the stored group without re-running the pick. A salt change
    # (prefix mismatch) or a stored group that no longer exists falls through to
    # re-bucket + overwrite.
    if sticky_store is not None and exp_name is not None:
        unit_entries = sticky_store.get(uid)
        entry = unit_entries.get(exp_name) if unit_entries else None
        if entry and entry.get("s") == salt8:
            for g in groups:
                if g.get("name") == entry.get("g"):
                    return _as_group(g)
            # Stored group gone — fall through to re-bucket + overwrite.

    # Allocation. Pooled (hashVersion ≥ 2 with a slice) gives real mutual
    # exclusion: the unit's universe segment must fall in the claimed range.
    # Legacy falls back to an independent per-experiment salt so siblings overlap.
    pool_offset = exp.get("poolOffsetBp")
    pool_size = exp.get("poolSizeBp")
    pooled = (
        (exp.get("hashVersion") or 1) >= 2
        and pool_offset is not None
        and pool_size is not None
        and pool_size > 0
    )
    if pooled:
        lo = pool_offset
        hi = lo + pool_size
        if universe_seg < lo or universe_seg >= hi:
            return _OUT
    else:
        alloc_pct = exp.get("allocationPct") or 0
        if murmur3(f"{salt}:alloc:{uid}") % 10000 >= alloc_pct:
            return _OUT

    # Group split over ``[0, usable)`` where ``usable = 10000 − reserved``; a unit
    # in the reserved tail is left unassigned so an appended variant can absorb it
    # (§B5).
    reserved = max(0, min(10000, exp.get("reservedHeadroomBp") or 0))
    usable = 10000 - reserved
    group_hash = murmur3(f"{salt}:group:{uid}") % 10000
    if group_hash >= usable:
        return _OUT
    cumulative = 0
    for i, g in enumerate(groups):
        cumulative += g.get("weight", 0)
        if group_hash < cumulative or i == len(groups) - 1:
            if sticky_store is not None and exp_name is not None:
                sticky_store.set(uid, exp_name, {"g": g.get("name", "control"), "s": salt8})
            return _as_group(g)

    return _OUT


def eval_experiment(
    exp: Optional[Mapping[str, Any]],
    flags_blob: Optional[Mapping[str, Any]],
    exps_blob: Optional[Mapping[str, Any]],
    user: Mapping[str, Any],
    *,
    exp_name: Optional[str] = None,
    sticky_store: Optional[StickyBucketStore] = None,
) -> ExperimentResult:
    """Evaluate a single running experiment to an :class:`ExperimentResult`
    (in-experiment + group + merged params). Internal seam: the public read path
    is ``universe(name).assign(user)``. A ``holdout``/``out`` standing collapses
    to the not-enrolled control result. Reused by the sticky-bucketing tests.
    """
    if not exp or exp.get("status") != "running":
        return ExperimentResult(in_experiment=False, group="control", params=None)

    universe_name = exp.get("universe")
    universe = (
        (exps_blob or {}).get("universes", {}).get(universe_name) if universe_name else None
    )
    holdout_range = universe.get("holdout_range") if universe else None
    param_defaults = param_defaults_from_schema(universe.get("param_schema") if universe else None)

    def _eval_gate_fn(gname: str) -> bool:
        gate = (flags_blob or {}).get("gates", {}).get(gname)
        return bool(gate and eval_gate(gate, user))

    standing = classify_experiment(
        exp,
        user,
        holdout_range,
        param_defaults,
        _eval_gate_fn,
        exp_name=exp_name,
        sticky_store=sticky_store,
    )
    if standing.state == "group":
        return ExperimentResult(
            in_experiment=True, group=standing.group or "control", params=standing.params
        )
    return ExperimentResult(in_experiment=False, group="control", params=None)


class Assignment:
    """The result of ``universe(name).assign(user)`` — a user's standing in a
    universe. A universe is a mutual-exclusion pool, so a unit lands in **at most
    one** experiment. Never throws: an un-enrolled unit still resolves ``get()``
    to the universe defaults (or your fallback).

    Exposure is logged **on read** (spec step 7): the single exposure fires the
    first time an enrolled unit's param is actually read via ``get()``, not at
    ``assign()`` time — so an assignment that is computed but never read logs
    nothing. Deduped per process; the durable per-(unit, experiment, group) dedup
    lives server-side. Pass ``exposure=False`` to read without logging (peek).
    """

    __slots__ = ("name", "group", "_params", "_on_expose", "_exposed")

    def __init__(
        self,
        name: Optional[str],
        group: Optional[str],
        # Already merged (universeDefaults ⊕ variantOverride) when enrolled;
        # defaults-only (or {}) when not.
        params: Optional[Mapping[str, Any]],
        # Fires the single exposure the first time an enrolled param is read.
        # ``None`` when not enrolled (nothing to expose). Deduped downstream.
        on_expose: Optional[Callable[[], None]] = None,
    ) -> None:
        self.name = name
        self.group = group
        self._params: Dict[str, Any] = dict(params) if params else {}
        self._on_expose = on_expose
        self._exposed = False

    @property
    def enrolled(self) -> bool:
        """True iff the unit is enrolled in an experiment in this universe.
        Reading it does NOT log an exposure (only ``get()`` of a param does)."""
        return self.group is not None

    def get(self, field: str, fallback: Any = None, *, exposure: bool = True) -> Any:
        """Read a resolved param: the assigned variant's override, else the
        universe default, else ``fallback``. Works even when not enrolled (the
        variant layer is absent, so you get ``universeDefault ?? fallback``). The
        first enrolled read logs the single exposure; pass ``exposure=False`` to
        suppress it (peek)."""
        # On-read exposure: the first param read of an enrolled assignment logs
        # one exposure, unless the caller opted out with ``exposure=False``.
        if exposure and not self._exposed and self._on_expose is not None:
            self._exposed = True
            self._on_expose()
        if field in self._params:
            return self._params[field]
        return fallback

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Assignment(name={self.name!r}, group={self.group!r})"
