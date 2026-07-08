"""Self-monitoring channel: when the SDK swallows an internal ("on our end")
error via the last-resort guard, it also ships a structured see event to
Shipeasy's OWN project — a baked-in destination + public client key, distinct
from the consumer's see() path. These tests pin the wire shape, the enable
gating, the dedup, and the no-throw guarantee.
"""

import json

import pytest

from shipeasy import _internal_report as ir
from shipeasy._internal_report import (
    report_internal_error,
    set_internal_report_context,
    INGEST_URL,
    PLACEHOLDER_KEY,
)

# A real-looking client key to exercise the send path (the baked default is an
# inert placeholder until the real key is minted).
FAKE_KEY = "sdk_client_testfakekey00000000000000000000"


@pytest.fixture
def sent(monkeypatch):
    """Capture /collect POSTs; run the daemon thread synchronously. Resets the
    channel to a clean, inert state and stands in a real-looking key."""
    ir._reset_internal_report_for_test()
    ir._set_internal_ingest_key_for_test(FAKE_KEY)

    captured = []

    # Run the fire-and-forget "thread" synchronously.
    monkeypatch.setattr(
        ir.threading,
        "Thread",
        lambda target, args, daemon: type(
            "Th", (), {"start": lambda self: target(*args)}
        )(),
    )

    def fake_send(url, key, data):
        captured.append(
            {"url": url, "key": key, "body": json.loads(data.decode("utf-8"))}
        )

    monkeypatch.setattr(ir, "_send", fake_send)
    yield captured
    ir._reset_internal_report_for_test()


def _event(captured):
    return captured[0]["body"]["events"][0]


# ---- destination + wire shape ----


def test_posts_to_baked_ingest_with_public_client_key(sent):
    set_internal_report_context(side="server", sdk_version="9.9.9")
    report_internal_error("flags.get", TypeError("cannot read foo"))
    assert len(sent) == 1
    assert sent[0]["url"] == INGEST_URL
    assert sent[0]["key"] == FAKE_KEY


def test_builds_stable_consequence_with_sdk_marker(sent):
    set_internal_report_context(side="server", sdk_version="9.9.9")
    report_internal_error("experiments.get", ValueError("boom"))
    ev = _event(sent)
    assert ev["type"] == "error"
    assert ev["kind"] == "caught"
    assert ev["subject"] == "experiments.get"
    assert ev["outcome"] == "returned a safe default"
    assert ev["error_type"] == "ValueError"
    assert ev["message"] == "boom"
    assert ev["side"] == "server"
    assert ev["sdk_version"] == "9.9.9"
    assert ev["extras"]["sdk"] == "python"


def test_does_not_attach_consumer_env(sent):
    set_internal_report_context(side="server", sdk_version="9.9.9")
    report_internal_error("killswitch.get", ValueError("x"))
    ev = _event(sent)
    assert "env" not in ev
    assert "url" not in ev


# ---- enable gating ----


def test_noop_before_context_set(sent):
    # No set_internal_report_context() call.
    report_internal_error("flags.get", ValueError("boom"))
    assert sent == []


def test_noop_when_disabled(sent):
    set_internal_report_context(side="server", sdk_version="9.9.9", enabled=False)
    report_internal_error("flags.get", ValueError("boom"))
    assert sent == []


def test_inert_while_ingest_key_is_placeholder(sent):
    ir._set_internal_ingest_key_for_test(PLACEHOLDER_KEY)
    set_internal_report_context(side="server", sdk_version="9.9.9")
    report_internal_error("flags.get", ValueError("boom"))
    assert sent == []


# ---- resilience ----


def test_dedupes_identical_errors_within_window(sent):
    set_internal_report_context(side="server", sdk_version="9.9.9")
    try:
        raise ValueError("same")
    except ValueError as err:
        # Same error object => same top stack frame => one fingerprint.
        report_internal_error("flags.get", err)
        report_internal_error("flags.get", err)
    assert len(sent) == 1


def test_never_raises_even_when_send_raises(sent, monkeypatch):
    def boom_send(url, key, data):
        raise RuntimeError("network down")

    monkeypatch.setattr(ir, "_send", boom_send)
    set_internal_report_context(side="server", sdk_version="9.9.9")
    # Must not propagate.
    report_internal_error("flags.get", ValueError("boom"))


# ---- guard integration ----


def test_engine_guard_reports_and_still_returns_fallback(sent, monkeypatch):
    from shipeasy import Engine

    # A real (non-test-mode) engine re-enables the channel with a live context.
    engine = Engine("srv_key", base_url="https://e.x")
    # Re-arm the fake key/reset that the Engine constructor's context call left
    # alone (the constructor only touches context, not the key), then force the
    # internal read to blow up so the last-resort guard fires.
    ir._set_internal_ingest_key_for_test(FAKE_KEY)
    monkeypatch.setattr(
        engine, "_get_config", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("internal invariant"))
    )

    out = engine.get_config("some_config", default="fallback")

    assert out == "fallback"
    assert len(sent) == 1
    ev = _event(sent)
    assert ev["subject"] == "configs.get"
    assert ev["message"] == "internal invariant"


def test_no_report_when_guard_body_succeeds(sent):
    from shipeasy import Engine

    engine = Engine("srv_key", base_url="https://e.x")
    ir._set_internal_ingest_key_for_test(FAKE_KEY)
    out = engine.get_killswitch("nonexistent")
    assert out is False
    assert sent == []
