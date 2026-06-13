from shipeasy._eval import eval_gate


# The no-unit evaluation rule is a cross-SDK contract: a request with no unit id
# answers a fully-rolled gate as on (no bucketing needed) but a fractional gate
# as off. See experiment-platform/18-identity-bucketing.md.
def test_no_unit_full_rollout_is_on():
    assert eval_gate({"enabled": 1, "salt": "s", "rolloutPct": 10000}, {}) is True


def test_no_unit_fractional_is_off():
    assert eval_gate({"enabled": 1, "salt": "s", "rolloutPct": 5000}, {}) is False


def test_no_unit_disabled_or_killed_is_off():
    assert eval_gate({"enabled": 0, "rolloutPct": 10000}, {}) is False
    assert eval_gate({"enabled": 1, "killswitch": 1, "rolloutPct": 10000}, {}) is False


def test_no_unit_targeting_rule_wins():
    gate = {
        "enabled": 1, "salt": "s", "rolloutPct": 10000,
        "rules": [{"attr": "plan", "op": "eq", "value": "pro"}],
    }
    assert eval_gate(gate, {}) is False
    assert eval_gate(gate, {"plan": "pro"}) is True


def test_with_unit_unchanged():
    assert eval_gate({"enabled": 1, "salt": "s", "rolloutPct": 0}, {"user_id": "u1"}) is False
    assert eval_gate({"enabled": 1, "salt": "s", "rolloutPct": 10000}, {"user_id": "u1"}) is True
