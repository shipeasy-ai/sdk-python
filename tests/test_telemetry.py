import hashlib

from shipeasy import _telemetry
from shipeasy._telemetry import Telemetry


def _capture(monkeypatch):
    sent = []
    # Run synchronously and record, instead of spawning daemon threads.
    monkeypatch.setattr(_telemetry, "_send", lambda url: sent.append(url))
    monkeypatch.setattr(
        _telemetry.threading,
        "Thread",
        lambda target, args, daemon: type("T", (), {"start": lambda self: target(*args)})(),
    )
    return sent


def test_emit_path_has_hash_not_raw_key(monkeypatch):
    sent = _capture(monkeypatch)
    t = Telemetry("https://t.example.com/", "sk_secret", side="server", env="prod")
    t.emit("gate", "checkout_v2")
    h = hashlib.sha256(b"sk_secret").hexdigest()
    assert sent == [f"https://t.example.com/t/{h}/server/prod/gate/checkout_v2"]
    assert "sk_secret" not in sent[0]


def test_percent_encodes_resource(monkeypatch):
    sent = _capture(monkeypatch)
    t = Telemetry("https://e.x", "k", side="client", env="prod")
    t.emit("config", "billing/plan name")
    assert sent[0].endswith("/config/billing%2Fplan%20name")


def test_dedup_window_collapses_repeats(monkeypatch):
    sent = _capture(monkeypatch)
    t = Telemetry("https://e.x", "k")
    for _ in range(50):
        t.emit("gate", "g")
    t.emit("gate", "other")
    assert len(sent) == 2


def test_disabled_and_empty_emit_nothing(monkeypatch):
    sent = _capture(monkeypatch)
    Telemetry("https://e.x", "k", disabled=True).emit("gate", "g")
    Telemetry("https://e.x", "").emit("gate", "g")
    Telemetry("", "k").emit("gate", "g")
    assert sent == []


# 1) basic telemetry send works for each entity call, hitting the right URL.
def test_client_fires_a_beacon_for_each_entity(monkeypatch):
    sent = _capture(monkeypatch)
    from shipeasy import Engine

    c = Engine("srv_key", base_url="https://e.x")
    c.get_flag("g", {"user_id": "u"})
    c.get_config("c")
    c.universe("e").assign({"user_id": "u"})
    assert len(sent) == 3
    assert any(u.endswith("/gate/g") for u in sent)
    assert any(u.endswith("/config/c") for u in sent)
    assert any(u.endswith("/experiment/e") for u in sent)


# 2) telemetry is not sent when disabled in settings.
def test_client_disable_telemetry_sends_nothing(monkeypatch):
    sent = _capture(monkeypatch)
    from shipeasy import Engine

    c = Engine("srv_key", base_url="https://e.x", disable_telemetry=True)
    c.get_flag("g", {"user_id": "u"})
    c.get_config("c")
    c.universe("e").assign({"user_id": "u"})
    assert sent == []
