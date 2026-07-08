"""Tests for the Django integration (``shipeasy.django``).

The pure settings-patch / env helpers are tested directly (no Django needed).
The management command + AppConfig + middleware tests boot a minimal Django and
self-skip via ``pytest.importorskip("django")`` so the SDK's normal CI (which
may not install Django) stays green.
"""
from __future__ import annotations

from pathlib import Path

import pytest

# Importing the command module pulls in Django, so the whole file is skipped when
# Django isn't installed (the SDK's normal CI installs only the openfeature extra).
pytest.importorskip("django")

from shipeasy.django.management.commands import shipeasy_install as cmd


# --------------------------------------------------------------------------- #
# Pure helpers — no Django required.                                            #
# --------------------------------------------------------------------------- #

SETTINGS_FIXTURE = '''\
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
]

ROOT_URLCONF = "myproject.urls"
'''


def test_patch_settings_adds_app_middleware_and_block():
    new, changed, manual = cmd.patch_settings(SETTINGS_FIXTURE)
    assert manual == []
    assert '"shipeasy.django",' in new
    assert '"shipeasy.django.middleware.AnonIdMiddleware",' in new
    assert "SHIPEASY = {" in new
    assert "SHIPEASY_SERVER_KEY" in new
    # Network egress is pinned to Django's production convention (not DEBUG).
    assert '"NETWORK_ENABLED": not DEBUG,' in new
    # The new app entry sits inside INSTALLED_APPS (before its closing bracket).
    apps_block = new[new.index("INSTALLED_APPS"): new.index("MIDDLEWARE")]
    assert '"shipeasy.django",' in apps_block
    assert len(changed) == 3


def test_patch_settings_is_idempotent():
    once, _, _ = cmd.patch_settings(SETTINGS_FIXTURE)
    twice, changed, manual = cmd.patch_settings(once)
    assert twice == once  # no further edits
    assert changed == []
    assert manual == []
    # No duplicate entries.
    assert once.count('"shipeasy.django",') == 1
    assert once.count('"shipeasy.django.middleware.AnonIdMiddleware",') == 1
    assert once.count("SHIPEASY = {") == 1


def test_patch_settings_missing_anchor_falls_back_to_manual():
    text = "# a settings file with no list literals\nDEBUG = True\n"
    new, changed, manual = cmd.patch_settings(text)
    # The SHIPEASY block can still be appended; the lists fall back to manual.
    assert "SHIPEASY = {" in new
    assert any("INSTALLED_APPS" in m for m in manual)
    assert any("MIDDLEWARE" in m for m in manual)


def test_patch_settings_partial_already_present():
    text = SETTINGS_FIXTURE.replace(
        '    "django.contrib.auth",\n',
        '    "django.contrib.auth",\n    "shipeasy.django",\n',
    )
    new, changed, manual = cmd.patch_settings(text)
    assert new.count('"shipeasy.django",') == 1  # not re-added
    assert any("MIDDLEWARE" in c for c in changed)
    assert "SHIPEASY = {" in new


def test_ensure_env_key_appends_once():
    text, changed = cmd.ensure_env_key("FOO=1\n")
    assert changed is True
    assert text == "FOO=1\nSHIPEASY_SERVER_KEY=\n"
    text2, changed2 = cmd.ensure_env_key(text)
    assert changed2 is False
    assert text2 == text


def test_ensure_env_key_empty_file():
    text, changed = cmd.ensure_env_key("")
    assert changed is True
    assert text == "SHIPEASY_SERVER_KEY=\n"


def test_ensure_os_import_added_when_missing():
    assert cmd.ensure_os_import("DEBUG = True\n").startswith("import os\n")
    assert cmd.ensure_os_import("import os\nDEBUG = True\n").count("import os") == 1
    assert cmd.ensure_os_import("from os import environ\n").count("import os") == 1


def test_settings_path_from_module(tmp_path: Path):
    pkg = tmp_path / "myproject"
    pkg.mkdir()
    (pkg / "settings.py").write_text("DEBUG = True\n")
    found = cmd.settings_path_from_module("myproject.settings", base_dir=tmp_path)
    assert found == pkg / "settings.py"
    assert cmd.settings_path_from_module(None, base_dir=tmp_path) is None
    assert cmd.settings_path_from_module("nope.settings", base_dir=tmp_path) is None


# --------------------------------------------------------------------------- #
# Django-backed tests — self-skip if Django isn't installed.                    #
# --------------------------------------------------------------------------- #


def _setup_django():
    """Configure + set up a minimal Django with shipeasy.django installed."""
    django = pytest.importorskip("django")
    from django.conf import settings as dj_settings

    if not dj_settings.configured:
        dj_settings.configure(
            DEBUG=True,
            INSTALLED_APPS=["shipeasy.django"],
            MIDDLEWARE=["shipeasy.django.middleware.AnonIdMiddleware"],
            DATABASES={},
            # No SHIPEASY dict → AppConfig.ready() warns + no-ops (so importing
            # the app never requires a real server key / network).
        )
        django.setup()
    return django


def test_django_setup_loads_app_without_server_key(recwarn):
    _setup_django()
    from django.apps import apps as dj_apps

    # The app is registered under our explicit label.
    app_cfg = dj_apps.get_app_config("shipeasy")
    assert app_cfg.name == "shipeasy.django"


def test_build_configure_kwargs():
    pytest.importorskip("django")
    from shipeasy.django.apps import build_configure_kwargs

    assert build_configure_kwargs(None) is None
    assert build_configure_kwargs({"SERVER_KEY": ""}) is None

    def attrs(u):
        return {"user_id": u}

    kwargs = build_configure_kwargs(
        {
            "SERVER_KEY": "sdk_server_x",
            "ATTRIBUTES": attrs,
            "ENV": "staging",
            "NETWORK_ENABLED": False,
            "DISABLE_TELEMETRY": True,
            "PRIVATE_ATTRIBUTES": ["email"],
            "BASE_URL": "https://flags.internal",
            "POLL": True,
        }
    )
    assert kwargs["api_key"] == "sdk_server_x"
    assert kwargs["attributes"] is attrs
    assert kwargs["env"] == "staging"
    assert kwargs["is_network_enabled"] is False
    assert kwargs["disable_telemetry"] is True
    assert kwargs["private_attributes"] == ["email"]
    assert kwargs["base_url"] == "https://flags.internal"
    assert kwargs["poll"] is True


def test_build_configure_kwargs_dotted_attributes():
    pytest.importorskip("django")
    from shipeasy.django.apps import build_configure_kwargs

    # Resolve a dotted path to a real callable. Use this module's actual import
    # name (pytest may import it as "test_django_install" with no tests package).
    dotted = f"{__name__}._sample_attrs"
    kwargs = build_configure_kwargs({"SERVER_KEY": "k", "ATTRIBUTES": dotted})
    resolved = kwargs["attributes"]
    assert callable(resolved)
    assert resolved(7) == {"user_id": "7"}  # the dotted callable, resolved
    # poll defaults False (Django request-scoped under WSGI).
    assert kwargs["poll"] is False


def _sample_attrs(u):  # referenced by the dotted-path test
    return {"user_id": str(u)}


def test_management_command_patches_tmp_settings(tmp_path: Path):
    _setup_django()
    from django.core.management import call_command

    settings_file = tmp_path / "settings.py"
    settings_file.write_text(SETTINGS_FIXTURE, encoding="utf-8")
    (tmp_path / ".env").write_text("EXISTING=1\n", encoding="utf-8")

    call_command("shipeasy_install", settings_file=str(settings_file))

    patched = settings_file.read_text(encoding="utf-8")
    assert '"shipeasy.django",' in patched
    assert '"shipeasy.django.middleware.AnonIdMiddleware",' in patched
    assert "SHIPEASY = {" in patched

    env = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "SHIPEASY_SERVER_KEY=" in env

    # Idempotent: a second run changes nothing.
    call_command("shipeasy_install", settings_file=str(settings_file))
    assert settings_file.read_text(encoding="utf-8") == patched


def test_management_command_no_env_flag(tmp_path: Path):
    _setup_django()
    from django.core.management import call_command

    settings_file = tmp_path / "settings.py"
    settings_file.write_text(SETTINGS_FIXTURE, encoding="utf-8")
    (tmp_path / ".env").write_text("EXISTING=1\n", encoding="utf-8")

    call_command("shipeasy_install", settings_file=str(settings_file), no_env=True)
    assert "SHIPEASY_SERVER_KEY" not in (tmp_path / ".env").read_text(encoding="utf-8")


def test_anon_id_middleware_sets_cookie_on_minted_id():
    _setup_django()
    from django.http import HttpResponse
    from shipeasy import _anon_id
    from shipeasy.django.middleware import AnonIdMiddleware

    captured = {}

    def get_response(request):
        captured["bound"] = _anon_id.current()
        captured["on_request"] = getattr(request, "shipeasy_anon_id", None)
        return HttpResponse("ok")

    mw = AnonIdMiddleware(get_response)

    class FakeRequest:
        COOKIES: dict = {}

        def is_secure(self):
            return True

    resp = mw(FakeRequest())
    cookie = resp.cookies.get(_anon_id.COOKIE)
    assert cookie is not None
    assert _anon_id.is_valid(cookie.value)
    assert captured["bound"] == cookie.value
    assert captured["on_request"] == cookie.value
    assert cookie["samesite"] == "Lax"
    assert cookie["secure"]
    # ContextVar cleared after the request.
    assert _anon_id.current() is None


def test_anon_id_middleware_reuses_valid_cookie():
    _setup_django()
    from django.http import HttpResponse
    from shipeasy import _anon_id
    from shipeasy.django.middleware import AnonIdMiddleware

    mw = AnonIdMiddleware(lambda request: HttpResponse("ok"))

    class FakeRequest:
        COOKIES = {_anon_id.COOKIE: "stable-1"}

        def is_secure(self):
            return False

    resp = mw(FakeRequest())
    # Existing valid id → no Set-Cookie.
    assert _anon_id.COOKIE not in resp.cookies
