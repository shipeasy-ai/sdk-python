"""Cross-language eval-parity golden-vector test.

Locks this SDK's bucketing to the platform's canonical implementation. The
fixture (``tests/fixtures/eval-vectors.json``) is copied byte-identically from
``packages/core/src/eval/__fixtures__/eval-vectors.json`` — every Shipeasy SDK
that reimplements bucketing MUST reproduce every vector. If a vector here ever
fails, bucketing has drifted from the platform and clients will be split
differently than the dashboard reports.

Hashed key formats (see the fixture ``$comment``):
  gate    = ``{salt}:{uid}``
  holdout = ``{universe}:{uid}``
  alloc   = ``{salt}:alloc:{uid}``
  group   = ``{salt}:group:{uid}``
  bucket  = murmur3(key) % 10000
"""

import json
import os

import pytest

from shipeasy._eval import eval_experiment, eval_gate
from shipeasy._hash import murmur3

_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "eval-vectors.json")

with open(_FIXTURE_PATH, encoding="utf-8") as _f:
    VECTORS = json.load(_f)


def _id(prefix, vectors):
    return [f"{prefix}[{i}] {v.get('note', v.get('input', ''))}" for i, v in enumerate(vectors)]


# --- (a) hash parity -------------------------------------------------------

_MASK32 = 0xFFFFFFFF


@pytest.mark.parametrize("vec", VECTORS["hash"], ids=_id("hash", VECTORS["hash"]))
def test_hash_vector(vec):
    # The fixture stores the unsigned 32-bit hash as a decimal; mask in case a
    # platform ever emits a signed value.
    assert murmur3(vec["input"]) == (vec["hash"] & _MASK32), vec["input"]


# --- (b) gate parity -------------------------------------------------------


@pytest.mark.parametrize("vec", VECTORS["gate"], ids=_id("gate", VECTORS["gate"]))
def test_gate_vector(vec):
    assert eval_gate(vec["gate"], vec["user"]) is vec["pass"]


# --- (c) experiment parity -------------------------------------------------


def _flags_blob(flags):
    """Translate the fixture's flat ``{gateName: bool}`` resolved-flag map into
    the ``{"gates": {name: gateDict}}`` shape ``eval_experiment`` reads, picking
    a gate definition that ``eval_gate`` resolves to the same bool for any
    identified unit (enabled+100% rollout → True, disabled → False)."""
    gates = {}
    for name, value in (flags or {}).items():
        gates[name] = {
            "enabled": bool(value),
            "rules": [],
            "rolloutPct": 10000,
            "salt": "",
        }
    return {"gates": gates}


def _exps_blob(exp, holdout_range):
    universe_name = exp.get("universe")
    universe = {}
    if holdout_range is not None:
        universe["holdout_range"] = holdout_range
    return {"universes": {universe_name: universe}}


@pytest.mark.parametrize("vec", VECTORS["experiment"], ids=_id("exp", VECTORS["experiment"]))
def test_experiment_vector(vec):
    exp = vec["experiment"]
    expected = vec["result"]

    result = eval_experiment(
        exp,
        _flags_blob(vec.get("flags")),
        _exps_blob(exp, vec.get("holdoutRange")),
        vec["user"],
    )

    assert result.in_experiment is expected["inExperiment"], vec["note"]
    if expected["inExperiment"]:
        assert result.group == expected["group"], vec["note"]
