import json

from shipeasy import Engine, InMemoryStickyStore
from shipeasy._eval import eval_experiment, pick_identifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _running_exp(salt="s", alloc=10000, groups=None, **extra):
    return {
        "status": "running",
        "salt": salt,
        "allocationPct": alloc,
        "groups": groups
        or [
            {"name": "control", "weight": 5000, "params": {"v": "c"}},
            {"name": "treatment", "weight": 5000, "params": {"v": "t"}},
        ],
        **extra,
    }


class _CaptureClient(Engine):
    """A non-test-mode client that captures /collect posts instead of sending
    them over the network. Lets us assert on outbound exposure/metric bodies."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.posts = []

    def _post_silent(self, path, data):  # capture instead of sending
        self.posts.append((path, json.loads(data.decode("utf-8"))))


def _make_capture_client(**kwargs):
    c = _CaptureClient(api_key="k", disable_telemetry=True, **kwargs)
    # Make track()/log_exposure() run the post inline so assertions are sync.
    import shipeasy._client as cm

    class _ImmediateThread:
        def __init__(self, target, args=(), daemon=False):
            self._target = target
            self._args = args

        def start(self):
            self._target(*self._args)

    c._orig_thread = cm.threading.Thread
    cm.threading.Thread = _ImmediateThread  # type: ignore[assignment]
    return c, cm


# ===========================================================================
# FEATURE A — private attributes
# ===========================================================================


def test_private_attributes_stripped_from_track():
    c, cm = _make_capture_client(private_attributes=["email", "ssn"])
    try:
        c.track("u1", "purchase", {"email": "a@b.c", "ssn": "123", "amount": 9})
    finally:
        cm.threading.Thread = c._orig_thread

    assert len(c.posts) == 1
    path, body = c.posts[0]
    assert path == "/collect"
    props = body["events"][0]["properties"]
    assert "email" not in props
    assert "ssn" not in props
    assert props == {"amount": 9}


def test_no_private_attributes_passes_props_through():
    c, cm = _make_capture_client()  # no private_attributes
    try:
        c.track("u1", "evt", {"a": 1, "b": 2})
    finally:
        cm.threading.Thread = c._orig_thread
    _, body = c.posts[0]
    assert body["events"][0]["properties"] == {"a": 1, "b": 2}


def test_private_attributes_still_drive_targeting():
    # A private attribute is stripped from /collect but still evaluable for
    # gate targeting (eval runs locally, before any strip).
    gate = {
        "enabled": 1,
        "rolloutPct": 10000,
        "salt": "s",
        "rules": [{"attr": "email", "op": "contains", "value": "@corp"}],
    }
    c = Engine.from_snapshot(flags={"gates": {"g": gate}}, experiments={})
    c._private_attributes = ["email"]
    assert c.get_flag("g", {"user_id": "u1", "email": "x@corp.com"}) is True
    assert c.get_flag("g", {"user_id": "u1", "email": "x@other.com"}) is False


# ===========================================================================
# FEATURE B — manual exposure (server)
# ===========================================================================


def test_log_exposure_once_when_enrolled():
    exps = {"experiments": {"exp": _running_exp(alloc=10000)}}
    c, cm = _make_capture_client()
    c._test_mode = False
    c._exps_blob = exps
    c._flags_blob = {}
    c._initialized = True
    try:
        c.log_exposure("u1", "exp")
    finally:
        cm.threading.Thread = c._orig_thread

    assert len(c.posts) == 1
    path, body = c.posts[0]
    assert path == "/collect"
    ev = body["events"][0]
    assert ev["type"] == "exposure"
    assert ev["experiment"] == "exp"
    assert ev["group"] in ("control", "treatment")
    assert ev["user_id"] == "u1"
    assert "ts" in ev


def test_log_exposure_noop_when_not_enrolled():
    # allocationPct = 0 → nobody enrolled → no exposure posted.
    exps = {"experiments": {"exp": _running_exp(alloc=0)}}
    c, cm = _make_capture_client()
    c._test_mode = False
    c._exps_blob = exps
    c._flags_blob = {}
    c._initialized = True
    try:
        c.log_exposure("u1", "exp")
    finally:
        cm.threading.Thread = c._orig_thread
    assert c.posts == []


def test_log_exposure_accepts_user_dict():
    exps = {"experiments": {"exp": _running_exp(alloc=10000)}}
    c, cm = _make_capture_client()
    c._test_mode = False
    c._exps_blob = exps
    c._flags_blob = {}
    c._initialized = True
    try:
        c.log_exposure({"user_id": "u9", "plan": "pro"}, "exp")
    finally:
        cm.threading.Thread = c._orig_thread
    assert len(c.posts) == 1
    ev = c.posts[0][1]["events"][0]
    assert ev["user_id"] == "u9"


def test_log_exposure_noop_in_test_mode():
    c = Engine.for_testing()
    # Even with an enrolled override, test-mode never touches the network.
    c.override_experiment("exp", "treatment", {})
    c.log_exposure("u1", "exp")  # must not raise


# ===========================================================================
# FEATURE C — sticky bucketing (server)
# ===========================================================================


def _eval(exp, user, store=None, name="exp"):
    return eval_experiment(
        exp,
        {},
        {},
        user,
        exp_name=name,
        sticky_store=store,
    )


def test_sticky_absent_is_deterministic():
    exp = _running_exp()
    user = {"user_id": "u1"}
    a = _eval(exp, user)
    b = _eval(exp, user)
    assert a.group == b.group  # deterministic with no store


def test_sticky_stores_on_fresh_pick():
    store = InMemoryStickyStore()
    exp = _running_exp(salt="abcdef0123456789")
    res = _eval(exp, {"user_id": "u1"}, store)
    assert res.in_experiment
    entry = store.get("u1")["exp"]
    assert entry["g"] == res.group
    assert entry["s"] == "abcdef01"  # salt[:8]


def test_sticky_survives_weight_change():
    # First pick stored; then weights flip so a fresh pick would land in the
    # OTHER group. With the same salt prefix the stored group must be returned.
    store = InMemoryStickyStore()
    exp1 = _running_exp(
        salt="saltsalt12345",
        groups=[
            {"name": "control", "weight": 10000, "params": {}},
            {"name": "treatment", "weight": 0, "params": {}},
        ],
    )
    first = _eval(exp1, {"user_id": "u1"}, store)
    assert first.group == "control"

    exp2 = _running_exp(
        salt="saltsalt12345",
        groups=[
            {"name": "control", "weight": 0, "params": {}},
            {"name": "treatment", "weight": 10000, "params": {}},
        ],
    )
    second = _eval(exp2, {"user_id": "u1"}, store)
    assert second.group == "control"  # stuck despite the weight flip


def test_sticky_survives_allocation_shrink():
    # Enroll at 100%, store the entry; shrink allocation to 0%. A non-sticky
    # eval would drop the user (alloc gate), but the stored entry skips it.
    store = InMemoryStickyStore()
    exp_full = _running_exp(salt="stickysalt99", alloc=10000)
    first = _eval(exp_full, {"user_id": "u1"}, store)
    assert first.in_experiment

    exp_shrunk = _running_exp(salt="stickysalt99", alloc=0)
    second = _eval(exp_shrunk, {"user_id": "u1"}, store)
    assert second.in_experiment
    assert second.group == first.group

    # Without the store, the shrink drops the user.
    assert _eval(exp_shrunk, {"user_id": "u1"}).in_experiment is False


def test_sticky_rebuckets_on_salt_change():
    # A salt change ⇒ stored prefix mismatch ⇒ re-bucket + overwrite the entry.
    store = InMemoryStickyStore(seed={"u1": {"exp": {"g": "treatment", "s": "OLDSALT0"}}})
    exp = _running_exp(salt="newsalt12345", alloc=10000)
    res = _eval(exp, {"user_id": "u1"}, store)
    # Returned group is a fresh deterministic pick, NOT necessarily "treatment".
    new_entry = store.get("u1")["exp"]
    assert new_entry["s"] == "newsalt1"  # overwritten with new salt prefix
    assert new_entry["g"] == res.group


def test_sticky_rebuckets_when_stored_group_missing():
    # Stored group no longer exists in the experiment ⇒ fall through, re-pick,
    # overwrite with a valid group.
    store = InMemoryStickyStore(
        seed={"u1": {"exp": {"g": "ghost", "s": "samesalt"}}}
    )
    exp = _running_exp(salt="samesalt9999", alloc=10000)
    # salt[:8] == "samesalt" matches the stored prefix, but group "ghost" is gone.
    res = _eval(exp, {"user_id": "u1"}, store)
    assert res.group in ("control", "treatment")
    assert store.get("u1")["exp"]["g"] == res.group


def test_sticky_keyed_by_bucket_by_unit():
    # When bucketBy is set, the sticky unit is the bucketBy-resolved identifier
    # (pick_identifier), not user_id.
    store = InMemoryStickyStore()
    exp = _running_exp(salt="orgsalt12345", alloc=10000, bucketBy="company_id")
    user = {"user_id": "u1", "company_id": "acme"}
    res = _eval(exp, user, store)
    assert res.in_experiment
    unit = pick_identifier(user, "company_id")
    assert unit == "acme"
    assert store.get("acme") is not None
    assert store.get("u1") is None


def test_sticky_via_client_get_experiment():
    store = InMemoryStickyStore()
    exps = {"experiments": {"exp": _running_exp(salt="clientsalt00", alloc=10000)}}
    c = Engine.from_snapshot(flags={}, experiments=exps)
    c._sticky_store = store
    first = c.get_experiment("exp", {"user_id": "u1"}, None)
    assert first.in_experiment
    assert store.get("u1")["exp"]["g"] == first.group
