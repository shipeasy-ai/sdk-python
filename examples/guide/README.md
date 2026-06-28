# Shipeasy · Python Entity Guide (Django example)

A single-page Django 5 app that reads like a "big guide document": one styled
card per Shipeasy entity — feature flag, dynamic config, A/B experiment, kill
switch, event/metric, i18n label, and `see()` error reporting. It runs
standalone with **no external services and zero network calls**.

## ⚠ SDK not wired yet

The `shipeasy` SDK is **intentionally not installed** in this example. Every
value you see on the page is a **hardcoded placeholder** defined in
[`guideapp/views.py`](guideapp/views.py). For each entity, the real SDK call is
captured twice:

- as a commented `# TODO: once \`shipeasy\` is installed` block in the view, and
- as a visible code block rendered on the page.

So nothing here authenticates, fetches, or evaluates anything yet — it's a
read-only reference you can run instantly and then make live.

## Run it

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver
```

Then open <http://127.0.0.1:8000>.

> No database migrations are needed — the page is a static view with no models.
> (Django still wants a `DATABASES` entry, so SQLite is configured but unused.)

## Next step: make it live

1. `pip install shipeasy`
2. Create one client at startup, e.g.
   ```python
   from shipeasy import Shipeasy, see
   client = Shipeasy(server_key=os.environ["SHIPEASY_SERVER_KEY"])
   ```
3. Open [`guideapp/views.py`](guideapp/views.py) and replace each placeholder in
   `ENTITIES` with the matching `# TODO` call — `client.get_flag(...)`,
   `client.get_config(...)`, `client.get_experiment(...)`, `client.evaluate(...)`,
   `client.track(...)`, and the `see(...)` error-reporting chain.

Docs: <https://docs.shipeasy.ai>
