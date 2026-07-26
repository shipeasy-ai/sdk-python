import html
import json

from shipeasy import Engine


def _client():
    return Engine.from_snapshot(
        flags={
            "gates": {
                "new_ui": {"enabled": True, "salt": "s", "rolloutPct": 10000},
                "off_gate": {"enabled": False, "salt": "s", "rolloutPct": 10000},
            },
            "configs": {"theme": {"value": {"color": "blue"}}},
        },
        experiments={"experiments": {}, "universes": {}},
    )


def test_evaluate_builds_payload():
    payload = _client().evaluate({"user_id": "u1"})
    assert payload["flags"]["new_ui"] is True
    assert payload["flags"]["off_gate"] is False
    assert payload["configs"]["theme"] == {"color": "blue"}
    assert payload["experiments"] == {}
    assert payload["killswitches"] == {}


def test_bootstrap_script_tag_attrs():
    tag = _client().bootstrap_script_tag({"user_id": "u1"}, anon_id="anon-1")
    assert 'src="https://cdn.shipeasy.ai/sdk/bootstrap.js"' in tag
    assert "data-se-bootstrap" in tag
    assert 'data-anon-id="anon-1"' in tag
    assert 'data-i18n-profile="en:prod"' in tag
    # No key of any kind.
    assert "data-key" not in tag
    # data-flags decodes back to valid JSON with the evaluated flag.
    raw = tag.split('data-flags="', 1)[1].split('"', 1)[0]
    assert json.loads(html.unescape(raw))["new_ui"] is True


def test_bootstrap_script_tag_omits_anon_when_unset():
    tag = _client().bootstrap_script_tag({"user_id": "u1"})
    assert "data-anon-id" not in tag


def test_bootstrap_script_tag_carries_identity_as_data_user():
    # A server-identified user rides the tag as data-user (minus anonymous_id),
    # so the browser SDK adopts the identity on first paint (no anon→identified flip).
    tag = _client().bootstrap_script_tag(
        {"user_id": "u1", "email": "u@x.test", "anonymous_id": "anon-1"},
        anon_id="anon-1",
    )
    raw = tag.split('data-user="', 1)[1].split('"', 1)[0]
    identity = json.loads(html.unescape(raw))
    assert identity == {"user_id": "u1", "email": "u@x.test"}
    # anonymous_id never leaks into data-user — it rides data-anon-id.
    assert "anonymous_id" not in identity
    assert 'data-anon-id="anon-1"' in tag


def test_bootstrap_script_tag_omits_data_user_when_anonymous():
    # No identified traits (anon-only, or empty) ⇒ no data-user, no PII on the tag.
    assert "data-user" not in _client().bootstrap_script_tag({"anonymous_id": "anon-1"})
    assert "data-user" not in _client().bootstrap_script_tag({})


def test_i18n_script_tag():
    tag = _client().i18n_script_tag("client_pub", "fr:prod")
    assert 'src="https://cdn.shipeasy.ai/sdk/i18n/loader.js"' in tag
    assert 'data-key="client_pub"' in tag
    assert 'data-profile="fr:prod"' in tag


# --- every argument is optional: the tags read what configure() set -----------


def _configured():
    return Engine.from_snapshot(
        flags={"gates": {}},
        experiments={"experiments": {}, "universes": {}},
        client_key="sdk_client_cfg",
        project_id="proj_cfg",
        profile="fr:prod",
        cdn_base_url="https://cdn.example.test",
    )


def test_i18n_script_tag_defaults_from_config():
    tag = _configured().i18n_script_tag()
    assert 'src="https://cdn.example.test/sdk/i18n/loader.js"' in tag
    assert 'data-key="sdk_client_cfg"' in tag
    assert 'data-profile="fr:prod"' in tag


def test_bootstrap_script_tag_needs_no_user():
    tag = _configured().bootstrap_script_tag()
    assert 'src="https://cdn.example.test/sdk/bootstrap.js"' in tag
    assert 'data-i18n-profile="fr:prod"' in tag
    assert "data-user" not in tag


def test_devtools_script_tag_defaults_from_config():
    tag = _configured().devtools_script_tag()
    assert 'src="https://cdn.example.test/se-devtools.js"' in tag
    assert 'data-project-id="proj_cfg"' in tag
    assert 'data-client-api-key="sdk_client_cfg"' in tag
    assert "defer" in tag


def test_explicit_arguments_still_win():
    engine = _configured()
    tag = engine.i18n_script_tag("other_key", "de:prod")
    assert 'data-key="other_key"' in tag and 'data-profile="de:prod"' in tag
    assert 'data-i18n-profile="de:prod"' in engine.bootstrap_script_tag(
        {"user_id": "u1"}, i18n_profile="de:prod"
    )
    dev = engine.devtools_script_tag("proj_other", client_key="other_key", defer=False)
    assert 'data-project-id="proj_other"' in dev
    assert 'data-client-api-key="other_key"' in dev
    assert "defer" not in dev


def test_tag_renders_and_warns_once_when_unconfigured(caplog):
    # A missing project id / client key still renders (the browser bundle
    # reports what it needs) but warns once per setting, not once per render.
    engine = _client()
    with caplog.at_level("WARNING", logger="shipeasy"):
        for _ in range(3):
            assert "se-devtools.js" in engine.devtools_script_tag()
    warnings = [r for r in caplog.records if "devtools_script_tag" in r.getMessage()]
    assert len(warnings) == 2  # project_id + client_key, once each
