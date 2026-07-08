"""Global pytest bootstrap for the SDK test suite.

The internal self-monitoring channel (``shipeasy._internal_report``) ships with a
REAL, baked-in production ingest key. That means any test which constructs a
reporting-enabled engine (a plain ``Engine(...)``, not ``Engine.for_testing()``)
and trips the last-resort guard could fire a real ``POST`` to
``api.shipeasy.ai/collect`` — polluting Shipeasy's own errors dashboard from CI.

To make that impossible, this autouse fixture resets the module-level ingest key
to the inert placeholder sentinel BEFORE every test, so the channel is inert by
default across the whole run — in any ordering, and when a single test runs in
isolation. Tests that deliberately exercise the send path (see
``test_internal_report.py``) request their own fixture, which runs after this one
and stands in a fake key + a stubbed ``_send``; so they still work and never
touch the network.
"""

import os

import pytest

from shipeasy import _internal_report as _ir


@pytest.fixture(autouse=True, scope="session")
def _egress_env_is_production():
    """Declare the test process production-equivalent for EGRESS decisions.

    The SDK's environment-derived defaults turn the master network switch and
    usage telemetry OFF outside production (see ``shipeasy/_env.py``). The suite
    runs in a non-production env, so without this the many tests that exercise a
    real network path (fetch, track, telemetry, see) would go silently offline
    and fail. Setting ``SHIPEASY_ENV=production`` for the whole run keeps those
    on-by-default; the dedicated tests in ``test_env_egress.py`` override the env
    locally (via monkeypatch) to assert the dev/prod branching itself.
    """
    prev = os.environ.get("SHIPEASY_ENV")
    os.environ["SHIPEASY_ENV"] = "production"
    yield
    if prev is None:
        os.environ.pop("SHIPEASY_ENV", None)
    else:
        os.environ["SHIPEASY_ENV"] = prev


@pytest.fixture(autouse=True)
def _internal_report_key_inert():
    """Force the internal-report ingest key to the inert placeholder before each
    test, so no test can fire a real internal-error send by default."""
    _ir._set_internal_ingest_key_for_test(_ir.PLACEHOLDER_KEY)
    yield
