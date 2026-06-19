from dataclasses import dataclass
from typing import Any, Mapping, Optional
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


_NOT_IN = ExperimentResult(in_experiment=False, group="control", params=None)


def eval_experiment(
    exp: Optional[Mapping[str, Any]],
    flags_blob: Optional[Mapping[str, Any]],
    exps_blob: Optional[Mapping[str, Any]],
    user: Mapping[str, Any],
    *,
    exp_name: Optional[str] = None,
    sticky_store: Optional[StickyBucketStore] = None,
) -> ExperimentResult:
    if not exp or exp.get("status") != "running":
        return _NOT_IN

    targeting_gate = exp.get("targetingGate")
    if targeting_gate:
        gate = (flags_blob or {}).get("gates", {}).get(targeting_gate)
        if not gate or not eval_gate(gate, user):
            return _NOT_IN

    # Bucket on exp.bucketBy (e.g. company_id) when set, else
    # user_id/anonymous_id. Holdout, allocation, and group all hash on the SAME
    # unit so a whole org moves together. No resolvable unit ⇒ not enrolled.
    uid = pick_identifier(user, exp.get("bucketBy"))
    if not uid:
        return _NOT_IN

    universe_name = exp.get("universe")
    universe = (exps_blob or {}).get("universes", {}).get(universe_name) if universe_name else None
    holdout = universe.get("holdout_range") if universe else None
    if holdout:
        seg = murmur3(f"{universe_name}:{uid}") % 10000
        if holdout[0] <= seg <= holdout[1]:
            return _NOT_IN

    salt = exp.get("salt") or ""
    groups = exp.get("groups") or []

    def _result_for_group(g: Mapping[str, Any]) -> ExperimentResult:
        return ExperimentResult(
            in_experiment=True, group=g.get("name", "control"), params=g.get("params")
        )

    # Sticky short-circuit (doc 20 §2): an enrolled unit whose stored salt prefix
    # still matches skips the allocation gate (so a shrinking allocation keeps it
    # in) and returns the stored group without re-running the pick. A salt change
    # (prefix mismatch) or a stored group that no longer exists falls through to
    # re-bucket + overwrite.
    salt8 = salt[:8]
    if sticky_store is not None and exp_name is not None:
        unit_entries = sticky_store.get(uid)
        entry = unit_entries.get(exp_name) if unit_entries else None
        if entry and entry.get("s") == salt8:
            for g in groups:
                if g.get("name") == entry.get("g"):
                    return _result_for_group(g)
            # Stored group gone — fall through to re-bucket + overwrite.

    alloc_pct = exp.get("allocationPct") or 0
    if murmur3(f"{salt}:alloc:{uid}") % 10000 >= alloc_pct:
        return _NOT_IN

    group_hash = murmur3(f"{salt}:group:{uid}") % 10000
    cumulative = 0
    for i, g in enumerate(groups):
        cumulative += g.get("weight", 0)
        if group_hash < cumulative or i == len(groups) - 1:
            if sticky_store is not None and exp_name is not None:
                sticky_store.set(uid, exp_name, {"g": g.get("name", "control"), "s": salt8})
            return _result_for_group(g)

    return _NOT_IN
