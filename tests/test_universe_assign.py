"""Universe-first assignment (the mutual-exclusion pool model, doc 20 §B).

``engine.universe(name).assign(user)`` returns an ``Assignment``: the ≤1
experiment the unit landed in within the universe, its variant, and resolved
params (variant override → universe default → fallback). These specs lock the
merge (§B2), the not-enrolled defaults path, pooled mutual exclusion (§B4),
reserved headroom (§B5), and the holdout gate (§B3). They seed the blobs directly
(no network) the way the eval-vectors test does. Mirrors ts-sdk's
``src/__tests__/universe-assign.test.ts``.
"""
from shipeasy import Engine
from shipeasy._hash import murmur3

MOD = 10000


def _universe_seg(universe: str, uid: str) -> int:
    return murmur3(f"{universe}:{uid}") % MOD


def _make_engine(flags: dict, exps: dict) -> Engine:
    client = Engine(api_key="test", base_url="http://localhost", disable_telemetry=True)
    client._flags_blob = {"gates": {}, "configs": {}, "killswitches": {}, **flags}
    client._exps_blob = {"universes": {}, "experiments": {}, **exps}
    client._initialized = True
    # Never touch the network from these tests (auto-exposure is a no-op).
    client._test_mode = True
    return client


# ---------------------------------------------------------------------------
# §B2 — param merge: variant override wins, universe defaults inherited.
# ---------------------------------------------------------------------------


def test_variant_override_wins_universe_default_inherited_unknown_fallback():
    engine = _make_engine(
        {},
        {
            "universes": {
                "u": {
                    "holdout_range": None,
                    "param_schema": [
                        {"name": "button_color", "type": "string", "default": "red"},
                        {"name": "size", "type": "int", "default": 1},
                    ],
                }
            },
            "experiments": {
                "exp": {
                    "universe": "u",
                    "allocationPct": 10000,
                    "salt": "s",
                    "status": "running",
                    "groups": [
                        {"name": "treatment", "weight": 10000, "params": {"button_color": "blue"}}
                    ],
                }
            },
        },
    )
    a = engine.universe("u").assign({"user_id": "u1"})
    assert a.enrolled is True
    assert a.group == "treatment"
    # Overridden by the variant.
    assert a.get("button_color") == "blue"
    # Not overridden → inherited from the universe default.
    assert a.get("size") == 1
    # Absent everywhere → the caller's fallback.
    assert a.get("missing", "fb") == "fb"


# ---------------------------------------------------------------------------
# Not enrolled still resolves to the universe defaults.
# ---------------------------------------------------------------------------


def test_not_enrolled_resolves_universe_default():
    engine = _make_engine(
        {},
        {
            "universes": {
                "u": {
                    "holdout_range": None,
                    "param_schema": [
                        {"name": "button_color", "type": "string", "default": "red"}
                    ],
                }
            },
            "experiments": {
                "exp": {
                    "universe": "u",
                    "allocationPct": 0,  # nobody allocated
                    "salt": "s",
                    "status": "running",
                    "groups": [
                        {"name": "treatment", "weight": 10000, "params": {"button_color": "blue"}}
                    ],
                }
            },
        },
    )
    a = engine.universe("u").assign({"user_id": "u1"})
    assert a.enrolled is False
    assert a.group is None
    # Not enrolled → universe default, not the variant override.
    assert a.get("button_color") == "red"


# ---------------------------------------------------------------------------
# §B4 — pooled mutual exclusion over ~400 synthetic users.
# ---------------------------------------------------------------------------


def test_pooled_mutual_exclusion():
    # Two experiments in ONE universe, hashVersion 2, disjoint pool slices:
    #   A = [0, 4000), B = [4000, 8000). Segment >= 8000 is unallocated headroom.
    engine = _make_engine(
        {},
        {
            "universes": {"u": {"holdout_range": None}},
            "experiments": {
                "expA": {
                    "universe": "u",
                    "hashVersion": 2,
                    "poolOffsetBp": 0,
                    "poolSizeBp": 4000,
                    "allocationPct": 10000,
                    "salt": "sA",
                    "status": "running",
                    "groups": [{"name": "A", "weight": 10000, "params": {}}],
                },
                "expB": {
                    "universe": "u",
                    "hashVersion": 2,
                    "poolOffsetBp": 4000,
                    "poolSizeBp": 4000,
                    "allocationPct": 10000,
                    "salt": "sB",
                    "status": "running",
                    "groups": [{"name": "B", "weight": 10000, "params": {}}],
                },
            },
        },
    )
    in_a = in_b = neither = 0
    for i in range(400):
        uid = f"u{i}"
        a = engine.universe("u").assign({"user_id": uid})
        # assign returns ≤1 experiment, so double-enrolment is impossible by
        # design; cross-check the landing against the unit's universe segment.
        seg = _universe_seg("u", uid)
        if a.name == "expA":
            in_a += 1
            assert seg < 4000
        elif a.name == "expB":
            in_b += 1
            assert 4000 <= seg < 8000
        else:
            neither += 1
            assert a.enrolled is False
            assert seg >= 8000
    # The partition is real: all three buckets are populated over 400 users.
    assert in_a > 0
    assert in_b > 0
    assert neither > 0
    assert in_a + in_b + neither == 400


# ---------------------------------------------------------------------------
# §B5 — reserved headroom leaves a not-enrolled tail.
# ---------------------------------------------------------------------------


def test_reserved_headroom_leaves_tail_unassigned():
    # 100% allocation, groups summing to 5000 with reservedHeadroomBp 5000: units
    # whose group hash falls in the reserved tail are left not-enrolled.
    engine = _make_engine(
        {},
        {
            "universes": {"u": {"holdout_range": None}},
            "experiments": {
                "exp": {
                    "universe": "u",
                    "allocationPct": 10000,
                    "reservedHeadroomBp": 5000,
                    "salt": "s",
                    "status": "running",
                    "groups": [{"name": "control", "weight": 5000, "params": {}}],
                }
            },
        },
    )
    enrolled = reserved = 0
    for i in range(400):
        a = engine.universe("u").assign({"user_id": f"u{i}"})
        if a.enrolled:
            enrolled += 1
        else:
            reserved += 1
    # Both populated: allocation is 100% yet the reserved tail carves out ~half.
    assert enrolled > 0
    assert reserved > 0


# ---------------------------------------------------------------------------
# §B3 — holdout gate forces holdout (not enrolled).
# ---------------------------------------------------------------------------


def test_holdout_gate_forces_holdout():
    engine = _make_engine(
        {
            "gates": {
                # enabled, 100% rollout, no rules → passes for every identified unit.
                "hg": {"rules": [], "rolloutPct": 10000, "salt": "hg", "enabled": 1},
            }
        },
        {
            "universes": {"u": {"holdout_range": None}},
            "experiments": {
                "exp": {
                    "universe": "u",
                    "holdoutGate": "hg",
                    "allocationPct": 10000,
                    "salt": "s",
                    "status": "running",
                    "groups": [{"name": "treatment", "weight": 10000, "params": {}}],
                }
            },
        },
    )
    a = engine.universe("u").assign({"user_id": "u1"})
    assert a.enrolled is False
    assert a.group is None


# ---------------------------------------------------------------------------
# Bound Client.universe(name).assign() — no user arg, uses bound attributes.
# ---------------------------------------------------------------------------


def test_bound_client_universe_assign(monkeypatch):
    import shipeasy
    from shipeasy import Client, configure, reset_global

    reset_global()
    try:
        snapshot = Engine.from_snapshot(
            flags={},
            experiments={
                "universes": {
                    "u": {
                        "holdout_range": None,
                        "param_schema": [
                            {"name": "button_color", "type": "string", "default": "red"}
                        ],
                    }
                },
                "experiments": {
                    "exp": {
                        "universe": "u",
                        "allocationPct": 10000,
                        "salt": "s",
                        "status": "running",
                        "groups": [
                            {"name": "treatment", "weight": 10000, "params": {"button_color": "blue"}}
                        ],
                    }
                },
            },
        )
        real_init = Engine.__init__

        def fake_init(self, api_key, *args, **kwargs):
            real_init(self, api_key, *args, **kwargs)
            self._test_mode = True
            self._flags_blob = dict(snapshot._flags_blob)
            self._exps_blob = dict(snapshot._exps_blob)
            self._initialized = True

        monkeypatch.setattr(Engine, "__init__", fake_init)
        configure(api_key="srv_key", init=False)

        a = Client({"user_id": "u1"}).universe("u").assign()  # no user arg
        assert a.enrolled is True
        assert a.group == "treatment"
        assert a.get("button_color") == "blue"

        # An unknown universe → not enrolled, empty defaults, safe get().
        b = Client({"user_id": "u1"}).universe("nope").assign()
        assert b.enrolled is False
        assert b.get("x", "fb") == "fb"
    finally:
        reset_global()


def test_override_experiment_surfaces_through_assign():
    # The override seam is still experiment-keyed; it surfaces via assign() when
    # the experiment exists (and is running) in the loaded blob.
    engine = _make_engine(
        {},
        {
            "universes": {"u": {"holdout_range": None}},
            "experiments": {
                "exp": {
                    "universe": "u",
                    "allocationPct": 0,  # would not enrol normally
                    "salt": "s",
                    "status": "running",
                    "groups": [{"name": "treatment", "weight": 10000, "params": {}}],
                }
            },
        },
    )
    engine.override_experiment("exp", "treatment", {"button_color": "green"})
    a = engine.universe("u").assign({"user_id": "u1"})
    assert a.enrolled is True
    assert a.group == "treatment"
    assert a.get("button_color") == "green"
