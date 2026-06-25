import json

import shipeasy
from shipeasy import Engine, see, see_violation, control_flow_exception
from shipeasy import _client, _see
from shipeasy._see import sanitize_extras, is_expected


def _capture(monkeypatch):
    """Capture /collect POST bodies; run the daemon thread synchronously."""
    sent = []
    monkeypatch.setattr(
        _client.threading,
        "Thread",
        lambda target, args, daemon: type(
            "Th", (), {"start": lambda self: target(*args)}
        )(),
    )

    def fake_post(self, path, data):
        sent.append((path, json.loads(data.decode("utf-8"))))

    monkeypatch.setattr(Engine, "_post_silent", fake_post)
    return sent


def _events(sent):
    return [e for path, body in sent for e in body["events"]]


def test_caught_exception_reports_error_event(monkeypatch):
    sent = _capture(monkeypatch)
    c = Engine("srv_key", base_url="https://e.x")
    try:
        raise ValueError("boom")
    except ValueError as e:
        c.see(e).causes_the("checkout").to("use cached prices")
    ev = _events(sent)[0]
    assert ev["type"] == "error"
    assert ev["kind"] == "caught"
    assert ev["error_type"] == "ValueError"
    assert ev["message"] == "boom"
    assert ev["subject"] == "checkout"
    assert ev["outcome"] == "use cached prices"
    assert ev["side"] == "server"
    assert ev["sdk_version"] == shipeasy.__version__
    assert ev["env"] == "prod"
    assert "stack" in ev


def test_extras_before_to_are_sanitized_and_sent(monkeypatch):
    sent = _capture(monkeypatch)
    c = Engine("srv_key", base_url="https://e.x")
    c.see(RuntimeError("x")).causes_the("photo upload").extras(
        {"photo_id": "p1", "size": 42, "ok": True, "skip": None}
    ).to("be rejected")
    ev = _events(sent)[0]
    assert ev["extras"] == {"photo_id": "p1", "size": 42, "ok": True}


def test_violation_uses_violation_kind(monkeypatch):
    sent = _capture(monkeypatch)
    c = Engine("srv_key", base_url="https://e.x")
    c.see_violation("large query").causes_the("search results").to("be trimmed")
    ev = _events(sent)[0]
    assert ev["kind"] == "violation"
    assert ev["error_type"] == "large query"
    assert ev["message"] == "large query"
    assert ev["subject"] == "search results"
    assert "stack" not in ev


def test_control_flow_marks_and_reports_nothing(monkeypatch):
    sent = _capture(monkeypatch)
    Engine("srv_key", base_url="https://e.x")
    e = ValueError("not a Foo")
    control_flow_exception(e).because("because it wasn't an encoded Foo").extras(
        {"tried": "Foo"}
    )
    assert is_expected(e)
    assert sent == []


def test_to_is_required_no_send_without_terminal(monkeypatch):
    sent = _capture(monkeypatch)
    c = Engine("srv_key", base_url="https://e.x")
    c.see(ValueError("x")).causes_the("checkout")  # no .to()
    assert sent == []


def test_to_is_idempotent(monkeypatch):
    sent = _capture(monkeypatch)
    c = Engine("srv_key", base_url="https://e.x")
    chain = c.see(ValueError("x")).causes_the("checkout")
    chain.to("a")
    chain.to("b")
    assert len(_events(sent)) == 1


def test_defaults_when_consequence_omitted(monkeypatch):
    sent = _capture(monkeypatch)
    c = Engine("srv_key", base_url="https://e.x")
    c.see(ValueError("x")).to("be incomplete")
    ev = _events(sent)[0]
    assert ev["subject"] == "app"


def test_test_mode_is_noop(monkeypatch):
    sent = _capture(monkeypatch)
    c = Engine.for_testing()
    c.see(ValueError("x")).causes_the("checkout").to("use cached prices")
    assert sent == []


def test_global_see_uses_last_constructed_client(monkeypatch):
    sent = _capture(monkeypatch)
    Engine("srv_key", base_url="https://e.x")
    see(ValueError("global")).causes_the("dashboard").to("show cached data")
    ev = _events(sent)[0]
    assert ev["subject"] == "dashboard"


def test_global_see_before_client_warns_and_drops(monkeypatch, caplog):
    _capture(monkeypatch)
    _see.set_default_client(None)
    see(ValueError("x")).causes_the("checkout").to("use cached prices")
    # No client → no crash, nothing sent.


def test_sanitize_extras_caps_keys_and_value_length():
    big = {f"k{i}": i for i in range(30)}
    big["long"] = "x" * 500
    out = sanitize_extras(big)
    assert len(out) <= 20


def test_private_attributes_stripped_from_extras(monkeypatch):
    sent = _capture(monkeypatch)
    c = Engine("srv_key", base_url="https://e.x", private_attributes=["secret"])
    c.see(ValueError("x")).causes_the("checkout").extras(
        {"secret": "shh", "ok": "yes"}
    ).to("use cached prices")
    ev = _events(sent)[0]
    assert "secret" not in ev["extras"]
    assert ev["extras"]["ok"] == "yes"
