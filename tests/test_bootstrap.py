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
