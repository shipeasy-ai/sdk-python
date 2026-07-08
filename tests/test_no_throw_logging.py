"""Runtime methods never raise + the leveled logger gates diagnostics.

Two guarantees are covered here:

1. A runtime read whose ``decode`` callback raises returns the documented safe
   default and never propagates the exception into the caller.
2. ``log_level`` gates the SDK's internal diagnostics: ``"silent"`` mutes every
   message; the default ``"warn"`` still emits a warn-level diagnostic.
"""
import logging

import pytest

import shipeasy
from shipeasy import Engine, configure_for_testing, reset_global
from shipeasy._eval import ExperimentResult
from shipeasy import _logging as _log


@pytest.fixture(autouse=True)
def _clean_global():
    reset_global()
    _log.set_log_level("warn")  # restore default between tests
    yield
    reset_global()
    _log.set_log_level("warn")


def _boom(_value):
    raise ValueError("decode blew up")


# ---- (a) runtime reads never raise on a failing decode ----


def test_get_config_bad_decode_returns_default_no_raise():
    configure_for_testing(configs={"cfg": {"any": "thing"}})
    client = shipeasy.Client({"user_id": "u1"})
    # Must NOT raise; returns the default.
    assert client.get_config("cfg", decode=_boom, default="fallback") == "fallback"


def test_get_experiment_bad_decode_returns_control_no_raise(monkeypatch):
    """A ``decode`` failure on an enrolled experiment returns a safe control
    result and never raises. The enrolled result is faked via ``eval_experiment``
    (the override path deliberately skips decode)."""
    from shipeasy import _client as client_mod

    engine = Engine.for_testing()
    # Force enrolment so the decode path is reached.
    monkeypatch.setattr(
        client_mod,
        "eval_experiment",
        lambda *a, **k: ExperimentResult(in_experiment=True, group="treatment", params={"raw": 1}),
    )
    result = engine.get_experiment("exp", {"user_id": "u1"}, default_params={"d": 0}, decode=_boom)
    assert isinstance(result, ExperimentResult)
    assert result.in_experiment is False
    assert result.group == "control"
    assert result.params == {"d": 0}


def test_engine_runtime_never_raises_on_unexpected_internal_error(monkeypatch):
    """An unexpected internal error inside a runtime read is swallowed and the
    documented safe default (default bool for get_flag) is returned."""
    engine = Engine.for_testing()

    def blow_up(*_a, **_k):
        raise RuntimeError("unexpected")

    # Break the inner implementation so the outer defensive catch is exercised.
    monkeypatch.setattr(engine, "_get_flag_detail", blow_up)
    assert engine.get_flag("whatever", {"user_id": "u1"}, default=True) is True


# ---- (b) log_level gates the diagnostics ----


def test_silent_mutes_warn(caplog):
    _log.set_log_level("silent")
    with caplog.at_level(logging.DEBUG, logger="shipeasy"):
        _log.warn("should be muted")
    assert caplog.records == []


def test_default_warn_emits(caplog):
    _log.set_log_level("warn")
    with caplog.at_level(logging.DEBUG, logger="shipeasy"):
        _log.warn("should be visible")
    assert any("should be visible" in r.getMessage() for r in caplog.records)


def test_warn_level_mutes_info_and_debug(caplog):
    _log.set_log_level("warn")
    with caplog.at_level(logging.DEBUG, logger="shipeasy"):
        _log.info("info hidden")
        _log.debug("debug hidden")
        _log.error("error shown")
    msgs = [r.getMessage() for r in caplog.records]
    assert "info hidden" not in msgs
    assert "debug hidden" not in msgs
    assert "error shown" in msgs


def test_invalid_level_is_ignored():
    _log.set_log_level("debug")
    _log.set_log_level("bogus-level")  # ignored, keeps current
    assert _log.get_log_level() == "debug"


def test_engine_log_level_option_sets_level():
    Engine.for_testing()  # default "warn"
    assert _log.get_log_level() == "warn"
    Engine(api_key="", disable_telemetry=True, log_level="silent")
    assert _log.get_log_level() == "silent"
