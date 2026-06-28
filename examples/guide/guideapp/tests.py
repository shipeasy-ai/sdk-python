"""
End-to-end test for the Shipeasy Python Entity Guide example.

This test demonstrates the SDK's TESTING setup: `configure_for_testing()`
mocks every value Shipeasy would return — no network, no api_key — and the
view reads them through the ordinary `shipeasy.Client(user)`, the same call
production code uses (see docs/pages/testing.md).

Because it runs IN-PROCESS via Django's test client, the
`configure_for_testing()` mock applied in `setUp` is the engine the view sees.

NOTE: The example view (guideapp/views.py) currently renders hardcoded
PLACEHOLDER values and is NOT wired to the SDK. The value assertions below are
therefore EXPECTED TO FAIL today — that is acceptable. What this test proves is
that the harness is correct: Django boots, the route is hit in-process, HTML
comes back, and the assertions run against the mocked values. Once the view is
wired to `shipeasy.Client(...)`, the assertions will pass with no test change.
"""

import shipeasy
from django.test import TestCase, Client


# Mocked values — exact ENTITY KEYS from guideapp/views.py, but DISTINCTIVE
# sentinel values that do NOT appear in the view's hardcoded placeholders. This
# is deliberate: if we sourced the mocks from the placeholder text, the page
# assertions would be tautological (matching the placeholders, not the SDK) and
# would falsely pass. With distinct sentinels the page assertions genuinely test
# the SDK→page path and therefore FAIL today (the view is not wired to the SDK).
MOCK_FLAG_NEW_CHECKOUT = True
MOCK_CONFIG_BILLING_COPY = {
    "headline": "Welcome aboard \U0001f680",  # "Welcome aboard 🚀"
    "cta": "Start free trial",
}
MOCK_EXPERIMENT_GROUP = "treatment"
MOCK_EXPERIMENT_PARAMS = {"color": "#0ea5e9", "label": "Checkout now"}


class GuidePageSdkValuesTest(TestCase):
    """Mock every Shipeasy value, fetch `/`, assert the page renders them."""

    def setUp(self):
        # Seed the test-mode engine. configure_for_testing() does zero network,
        # needs no api_key, and REPLACES any previously-configured engine, so
        # each test reconfigures freely with no reset boilerplate.
        shipeasy.configure_for_testing(
            flags={"new_checkout": MOCK_FLAG_NEW_CHECKOUT},
            configs={"billing_copy": MOCK_CONFIG_BILLING_COPY},
            experiments={
                "checkout_button": (MOCK_EXPERIMENT_GROUP, MOCK_EXPERIMENT_PARAMS),
            },
        )
        self.client = Client()

    def test_mock_setup_reads_back_through_client(self):
        """Sanity-check the testing API itself: the values read back as mocked.

        This isolates the SDK testing surface from the (currently unwired) view,
        so this part stays green regardless of the view wiring.
        """
        se = shipeasy.Client({"user_id": "u_123"})

        self.assertIs(se.get_flag("new_checkout"), True)
        self.assertEqual(se.get_config("billing_copy"), MOCK_CONFIG_BILLING_COPY)

        result = se.get_experiment(
            "checkout_button",
            default_params={"color": "#888", "label": "Buy"},
        )
        self.assertTrue(result.in_experiment)
        self.assertEqual(result.group, MOCK_EXPERIMENT_GROUP)
        self.assertEqual(result.params, MOCK_EXPERIMENT_PARAMS)

    def test_guide_page_renders_mocked_sdk_values(self):
        """Fetch the page in-process and assert the HTML contains the mocks.

        EXPECTED TO FAIL until guideapp/views.py is wired to the SDK — the view
        still renders hardcoded placeholders. The harness around it is correct.
        """
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

        html = response.content.decode()

        # Feature flag `new_checkout` → True
        self.assertIn("True", html)

        # Dynamic config `billing_copy` → each mocked value
        self.assertIn(MOCK_CONFIG_BILLING_COPY["headline"], html)
        self.assertIn(MOCK_CONFIG_BILLING_COPY["cta"], html)

        # A/B experiment `checkout_button` → group + params
        self.assertIn(MOCK_EXPERIMENT_GROUP, html)
        self.assertIn(MOCK_EXPERIMENT_PARAMS["color"], html)
        self.assertIn(MOCK_EXPERIMENT_PARAMS["label"], html)
