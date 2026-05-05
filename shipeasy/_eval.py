from dataclasses import dataclass
from typing import Any, Mapping, Optional
import re

from ._hash import murmur3


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
        return False
    salt = gate.get("salt") or ""
    return murmur3(f"{salt}:{uid}") % 10000 < (gate.get("rolloutPct") or 0)


_NOT_IN = ExperimentResult(in_experiment=False, group="control", params=None)


def eval_experiment(
    exp: Optional[Mapping[str, Any]],
    flags_blob: Optional[Mapping[str, Any]],
    exps_blob: Optional[Mapping[str, Any]],
    user: Mapping[str, Any],
) -> ExperimentResult:
    if not exp or exp.get("status") != "running":
        return _NOT_IN

    targeting_gate = exp.get("targetingGate")
    if targeting_gate:
        gate = (flags_blob or {}).get("gates", {}).get(targeting_gate)
        if not gate or not eval_gate(gate, user):
            return _NOT_IN

    uid = _user_id(user)
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
    alloc_pct = exp.get("allocationPct") or 0
    if murmur3(f"{salt}:alloc:{uid}") % 10000 >= alloc_pct:
        return _NOT_IN

    group_hash = murmur3(f"{salt}:group:{uid}") % 10000
    cumulative = 0
    groups = exp.get("groups") or []
    for i, g in enumerate(groups):
        cumulative += g.get("weight", 0)
        if group_hash < cumulative or i == len(groups) - 1:
            return ExperimentResult(in_experiment=True, group=g.get("name", "control"), params=g.get("params"))

    return _NOT_IN
