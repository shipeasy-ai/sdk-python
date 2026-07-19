"""Gatekeeper ``stack`` evaluation in the server SDK.

Regression guard for the bug where ``eval_gate`` read only the flat
``rules``+``rolloutPct`` columns and ignored a modern gate's ordered ``stack``.
The canonical model is the stack (mirrors ``@shipeasy/core`` ``evalGatekeeper`` +
the edge worker); the flat columns are a lossy approximation that can invert the
result (a whitelist condition at 100% followed by a 0% public rollout flattens to
``rolloutPct: 0``). These vectors lock the SDK to the stack.
"""
from shipeasy._eval import eval_gate

MOD = 10000

P = "e976b15e-3ccc-44d3-821d-87f06d5a0e43"


def _whitelist_gate():
    """The exact shape the KV rebuild ships for a whitelist gatekeeper: a
    condition (no explicit rolloutPct ⇒ 100%) whitelisting a project, then a
    locked 0% public rollout. The flat columns are the lossy approximation."""
    return {
        "name": "release_module",
        "enabled": 1,
        "salt": "caf3a1ae",
        # Lossy flat approximation — must NOT be what decides the result.
        "rules": [{"attr": "project_id", "op": "in", "value": [P]}],
        "rolloutPct": 0,
        "stack": [
            {
                "id": "gq578snc",
                "type": "condition",
                "pass": "all",
                "rules": [{"attr": "project_id", "op": "in", "value": [P]}],
            },
            {"id": "gu0uein4", "type": "rollout", "rolloutPct": 0, "bucketBy": "user_id", "salt": "public"},
        ],
    }


def test_whitelisted_caller_passes_despite_flat_rollout_zero():
    # The regression: the flat path would read "matches whitelist AND 0% bucket"
    # = False. The stack short-circuits on the 100% condition → True.
    user = {"user_id": "cdewqzx@gmail.com", "project_id": P}
    assert eval_gate(_whitelist_gate(), user) is True


def test_non_whitelisted_caller_hidden():
    # Condition misses, public rollout is 0% → off.
    user = {"user_id": "someone@else.com", "project_id": "other-project"}
    assert eval_gate(_whitelist_gate(), user) is False


def test_whitelisted_caller_with_no_identity_passes():
    # No user_id/anonymous_id: a fully-rolled (100%) condition is answerable
    # without a unit id.
    assert eval_gate(_whitelist_gate(), {"project_id": P}) is True


def test_matching_condition_still_gates_on_its_own_rollout():
    gate = {
        "name": "g",
        "enabled": 1,
        "salt": "s",
        "rules": [],
        "rolloutPct": 0,
        "stack": [
            {
                "id": "c1",
                "type": "condition",
                "pass": "all",
                "rules": [{"attr": "project_id", "op": "in", "value": [P]}],
                "rolloutPct": 0,  # matched but 0% → never
            },
        ],
    }
    assert eval_gate(gate, {"user_id": "u1", "project_id": P}) is False


def test_pass_any_condition():
    gate = {
        "name": "g",
        "enabled": 1,
        "salt": "s",
        "rules": [],
        "rolloutPct": 0,
        "stack": [
            {
                "id": "c1",
                "type": "condition",
                "pass": "any",
                "rules": [
                    {"attr": "plan", "op": "eq", "value": "pro"},
                    {"attr": "project_id", "op": "in", "value": [P]},
                ],
            },
        ],
    }
    # plan misses but project_id matches → one branch is enough for pass:any.
    assert eval_gate(gate, {"user_id": "u", "plan": "free", "project_id": P}) is True
    assert eval_gate(gate, {"user_id": "u", "plan": "free", "project_id": "x"}) is False


def test_falls_through_to_catch_all_rollout():
    gate = {
        "name": "g",
        "enabled": 1,
        "salt": "s",
        "rules": [],
        "rolloutPct": 0,
        "stack": [
            {
                "id": "c1",
                "type": "condition",
                "pass": "all",
                "rules": [{"attr": "project_id", "op": "in", "value": [P]}],
            },
            {"id": "public", "type": "rollout", "rolloutPct": MOD},  # everyone else: 100%
        ],
    }
    assert eval_gate(gate, {"user_id": "u", "project_id": "not-whitelisted"}) is True


def test_disabled_or_killed_stacked_gate_is_off():
    base = _whitelist_gate()
    disabled = dict(base, enabled=0)
    assert eval_gate(disabled, {"user_id": "u", "project_id": P}) is False
    killed = dict(base, killswitch=1)
    assert eval_gate(killed, {"user_id": "u", "project_id": P}) is False


def test_stackless_gate_uses_legacy_flat_path():
    on = {"name": "on", "enabled": 1, "salt": "s", "rules": [], "rolloutPct": MOD}
    off = {"name": "off", "enabled": 1, "salt": "s", "rules": [], "rolloutPct": 0}
    assert eval_gate(on, {"user_id": "u"}) is True
    assert eval_gate(off, {"user_id": "u"}) is False


def test_empty_stack_falls_back_to_flat():
    # An explicitly empty stack must not short-circuit to False — legacy flat
    # behaviour still applies.
    gate = {"name": "g", "enabled": 1, "salt": "s", "rules": [], "rolloutPct": MOD, "stack": []}
    assert eval_gate(gate, {"user_id": "u"}) is True
