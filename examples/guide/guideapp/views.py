"""
Shipeasy · Python Entity Guide — the single guide view.

⚠ THE SDK IS NOT WIRED YET.

Every value rendered on the page is a hardcoded placeholder defined right
here in `ENTITIES`. For each entity, the REAL Shipeasy SDK call is captured
twice:

  1. As a commented `# TODO: once `shipeasy` is installed` block below, so a
     reader can copy it straight into their own code.
  2. As the `call` string on the entity dict, which the template renders as a
     visible code block next to the placeholder value.

Once you `pip install shipeasy`, create a client once at startup, e.g.

    # from shipeasy import Shipeasy, see
    # client = Shipeasy(server_key=os.environ["SHIPEASY_SERVER_KEY"])

and replace each placeholder below with the matching live call.
"""

from django.shortcuts import render


# ---------------------------------------------------------------------------
# REAL SDK CALLS — kept as TODO blocks so they're easy to copy into real code.
# None of these run today; the SDK is not installed. See each entity's `call`
# field for the same snippet rendered on the page.
# ---------------------------------------------------------------------------

# 1. Feature flag
#    TODO: once `shipeasy` is installed
#    on = client.get_flag("new_checkout", {"user_id": "u_123"})

# 2. Dynamic config
#    TODO: once `shipeasy` is installed
#    cfg = client.get_config("billing_copy")

# 3. A/B experiment
#    TODO: once `shipeasy` is installed
#    r = client.get_experiment(
#        "checkout_button",
#        user={"user_id": "u_123"},
#        default_params={"color": "#888", "label": "Buy"},
#    )
#    # r.in_experiment, r.group, r.params

# 4. Kill switch
#    TODO: once `shipeasy` is installed
#    boot = client.evaluate({"user_id": "u_123"})
#    paused = boot["killswitches"]["payments_paused"]

# 5. Event / metric
#    TODO: once `shipeasy` is installed
#    client.track("u_123", "checkout_completed", {"revenue": 49.99, "plan": "pro"})

# 6. i18n label (illustrative — the Python i18n entry-point ships as a follow-up)
#    TODO: once `shipeasy` is installed
#    t("hero.title", {"name": "Sam"})

# 7. Error reporting — see()
#    TODO: once `shipeasy` is installed
#    try:
#        submit_order(o)
#    except Exception as e:
#        see(e).causes_the("checkout").to("use cached prices").extras(order_id=o.id)


ENTITIES = [
    {
        "label": "Feature Flag",
        "accent": "#34d399",
        "key": "new_checkout",
        "value": "True",
        "value_meta": "reason: RULE_MATCH",
        "description": "A boolean on/off switch with targeting rules + percentage rollout.",
        "call": 'on = client.get_flag("new_checkout", {"user_id": "u_123"})',
        "meta": "Placeholder · would resolve per-user against your rollout rules.",
    },
    {
        "label": "Dynamic Config",
        "accent": "#60a5fa",
        "key": "billing_copy",
        "value": '{"headline": "Welcome back \U0001f44b", "cta": "Upgrade to Pro"}',
        "value_meta": "typed JSON",
        "description": "A typed JSON blob you change without deploying.",
        "call": 'cfg = client.get_config("billing_copy")',
        "meta": "Placeholder · edit + publish from the dashboard, no redeploy.",
    },
    {
        "label": "A/B Experiment",
        "accent": "#c084fc",
        "key": "checkout_button",
        "value": 'in_experiment=True · group="treatment"',
        "value_meta": 'params: {"color": "#34d399", "label": "Buy now"}',
        "description": "Splits users into variants and measures a metric.",
        "call": (
            'r = client.get_experiment(\n'
            '    "checkout_button",\n'
            '    user={"user_id": "u_123"},\n'
            '    default_params={"color": "#888", "label": "Buy"},\n'
            ')\n'
            '# r.in_experiment, r.group, r.params'
        ),
        "meta": "Placeholder · bucketing + exposure logging happen server-side.",
    },
    {
        "label": "Kill Switch",
        "accent": "#f87171",
        "key": "payments_paused",
        "value": "False",
        "value_meta": "payments live",
        "description": (
            "An operational off-switch shipped alongside flags — flip it to "
            "disable a subsystem during an incident."
        ),
        "call": (
            'boot = client.evaluate({"user_id": "u_123"})\n'
            'paused = boot["killswitches"]["payments_paused"]'
        ),
        "meta": "Placeholder · rides the same KV blob as your flags + configs.",
    },
    {
        "label": "Event / Metric",
        "accent": "#22d3ee",
        "key": "checkout_completed",
        "value": "last event queued",
        "value_meta": 'props: {"revenue": 49.99, "plan": "pro"}',
        "description": "Fire-and-forget events that power experiment metrics + dashboards.",
        "call": 'client.track("u_123", "checkout_completed", {"revenue": 49.99, "plan": "pro"})',
        "meta": "Placeholder · non-blocking; flushed to Analytics Engine.",
    },
    {
        "label": "i18n Label",
        "accent": "#fbbf24",
        "key": "hero.title",
        "value": "Ship features, not stress",
        "value_meta": "server-managed copy",
        "description": (
            "Server-managed copy you translate + publish from the dashboard — "
            "no redeploy. (i18n for the Python SDK ships as a follow-up "
            "sub-entry-point; shown here for completeness.)"
        ),
        "call": 't("hero.title", {"name": "Sam"})',
        "meta": "Placeholder · illustrative call — Python i18n entry-point is upcoming.",
    },
    {
        "label": "Error Reporting",
        "accent": "#f87171",
        "key": "see()",
        "value": "0 issues reported this session",
        "value_meta": "structured reports",
        "description": (
            "Structured error reports that document the product consequence, "
            "not just a stack trace."
        ),
        "call": (
            "try:\n"
            "    submit_order(o)\n"
            "except Exception as e:\n"
            '    see(e).causes_the("checkout").to("use cached prices").extras(order_id=o.id)'
        ),
        "meta": "Placeholder · captures the consequence, not just the traceback.",
    },
]


def guide(request):
    context = {
        "title": "Shipeasy · Python Entity Guide",
        "subtitle": (
            "One card per Shipeasy entity — feature flags, configs, "
            "experiments, kill switches, events, i18n, and error reporting."
        ),
        "banner": (
            "⚠ SDK not wired yet — every value below is a placeholder. "
            "Install shipeasy and replace the TODOs to make them live."
        ),
        "entities": ENTITIES,
    }
    return render(request, "guide.html", context)
