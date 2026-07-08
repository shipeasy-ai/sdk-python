"""``python manage.py shipeasy_install`` — wire Shipeasy into a Django project.

The Django-native equivalent of ``rails generate shipeasy:install``: it
idempotently patches your settings file to

  * add ``"shipeasy.django"`` to ``INSTALLED_APPS`` (so the AppConfig's
    ``ready()`` calls ``shipeasy.configure`` from the ``SHIPEASY`` settings dict),
  * add ``"shipeasy.django.middleware.AnonIdMiddleware"`` to ``MIDDLEWARE`` (the
    shared ``__se_anon_id`` cookie), and
  * append a ``SHIPEASY = {...}`` config block (reading env via ``os.environ``)
    if one is absent,

and (unless ``--no-env``) appends ``SHIPEASY_SERVER_KEY=`` to any existing
``.env`` / ``.env.example``. Every edit is anchored + idempotent; when it cannot
confidently edit, it prints the exact block to paste instead of corrupting the
file.

The file/env logic lives in module-level pure functions (``patch_settings``,
``ensure_env_key``, …) so it is unit-testable without booting Django.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

from django.core.management.base import BaseCommand, CommandError

INSTALLED_APP = "shipeasy.django"
MIDDLEWARE_PATH = "shipeasy.django.middleware.AnonIdMiddleware"
ENV_KEY = "SHIPEASY_SERVER_KEY"

# The SHIPEASY config block appended to settings.py when absent. ``os`` is used,
# but settings.py virtually always imports it already; ensure_os_import() adds it
# if missing.
SHIPEASY_BLOCK = """\
# --- Shipeasy (feature flags, configs, kill switches, A/B experiments) ---------
# Read more: https://docs.shipeasy.ai  ·  Mint keys: https://app.shipeasy.ai
# configure() runs once at boot from this dict (shipeasy.django AppConfig.ready);
# then read per request: shipeasy.Client(request.user).get_flag("new_checkout").
SHIPEASY = {
    # Required — your Shipeasy SERVER key (sdk_server_...). A server-side secret;
    # never embed it in the browser. Read it from the environment.
    "SERVER_KEY": os.environ.get("SHIPEASY_SERVER_KEY"),
    # Network egress — the master switch for ALL outbound requests (flag fetches,
    # track, exposures, see() reports, usage telemetry, internal self-monitoring).
    # Pinned to Django's production convention (DEBUG is False in production) so
    # the SDK is fully active in prod and stays completely quiet in dev/CI — reads
    # return your in-code defaults there. Set True to force flags to load in dev.
    "NETWORK_ENABLED": not DEBUG,
    # Optional — map YOUR user object to the Shipeasy attribute map targeting
    # evaluates against. A dotted import path to a callable, or a callable.
    # "ATTRIBUTES": lambda u: {"user_id": str(u.id), "plan": getattr(u, "plan", None)},
    # Optional — environment tag on see()/usage telemetry. Default "prod".
    # "ENV": "prod",
    # Long-running server (gunicorn/uwsgi): keep flags fresh with the background
    # poll. Leave False (default) for serverless / short-lived processes.
    "POLL": False,
}
# ------------------------------------------------------------------------------
"""


# --------------------------------------------------------------------------- #
# Pure, Django-free helpers (unit-testable against tmp files / strings).        #
# --------------------------------------------------------------------------- #


def _has_app(text: str) -> bool:
    return bool(re.search(rf"""["']{re.escape(INSTALLED_APP)}["']""", text))


def _has_middleware(text: str) -> bool:
    return bool(re.search(rf"""["']{re.escape(MIDDLEWARE_PATH)}["']""", text))


def _has_shipeasy_block(text: str) -> bool:
    return bool(re.search(r"""^SHIPEASY\s*=""", text, re.MULTILINE))


def _list_anchor(text: str, name: str) -> Optional[re.Match]:
    """Match an ``NAME = [`` assignment (the opening of a list literal)."""
    return re.search(rf"""^{name}\s*=\s*\[""", text, re.MULTILINE)


def _insert_into_list(text: str, name: str, entry: str) -> Optional[str]:
    """Insert ``"entry",`` as the last element of the ``NAME = [ ... ]`` literal.

    Returns the patched text, or ``None`` if no single-anchor list literal could
    be found (caller falls back to printing the manual instruction).
    """
    m = _list_anchor(text, name)
    if not m:
        return None
    # Find the matching closing bracket for the list that opens at m.end()-1.
    open_idx = text.index("[", m.start())
    depth = 0
    close_idx = None
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                close_idx = i
                break
    if close_idx is None:
        return None

    inner = text[open_idx + 1 : close_idx]
    # Indentation: reuse the first existing element's indent, else 4 spaces.
    indent_match = re.search(r"\n([ \t]+)\S", inner)
    indent = indent_match.group(1) if indent_match else "    "
    addition = f'{indent}"{entry}",\n'

    # Place before the closing bracket, preserving a trailing newline if present.
    head = text[: close_idx]
    tail = text[close_idx:]
    if not head.endswith("\n"):
        head += "\n"
    return head + addition + tail


def ensure_os_import(text: str) -> str:
    """Make sure the ``os`` name is bound (the SHIPEASY block uses ``os.environ``).

    Only ``import os`` (optionally ``as os``) binds the ``os`` name;
    ``from os import ...`` does NOT, so we still prepend ``import os`` in that
    case. Idempotent on an existing ``import os``.
    """
    # A top-level `import os`, `import os, sys`, or `import os as os` binds `os`.
    # `from os import ...` does not, so it is intentionally not matched here.
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "import os" or stripped.startswith("import os "):
            tail = stripped[len("import os"):].lstrip()
            if tail == "" or tail.startswith(",") or tail.startswith("as os"):
                return text
        if stripped.startswith("import ") and re.search(r"\bos\b", stripped.split("import", 1)[1].split(" as ")[0]):
            # e.g. `import sys, os`
            return text
    return "import os\n" + text


def patch_settings(text: str) -> Tuple[str, List[str], List[str]]:
    """Apply all idempotent settings edits to ``text``.

    Returns ``(new_text, changed, manual)`` where ``changed`` lists the human
    descriptions of edits made and ``manual`` lists instructions for edits that
    could not be applied safely (so the caller can print them to paste by hand).
    Re-running on already-patched text yields no changes and no manual steps.
    """
    changed: List[str] = []
    manual: List[str] = []
    new = text

    # 1) INSTALLED_APPS
    if _has_app(new):
        pass
    else:
        patched = _insert_into_list(new, "INSTALLED_APPS", INSTALLED_APP)
        if patched is not None:
            new = patched
            changed.append(f'added "{INSTALLED_APP}" to INSTALLED_APPS')
        else:
            manual.append(
                f'Add "{INSTALLED_APP}" to your INSTALLED_APPS list.'
            )

    # 2) MIDDLEWARE
    if _has_middleware(new):
        pass
    else:
        patched = _insert_into_list(new, "MIDDLEWARE", MIDDLEWARE_PATH)
        if patched is not None:
            new = patched
            changed.append(f'added "{MIDDLEWARE_PATH}" to MIDDLEWARE')
        else:
            manual.append(
                f'Add "{MIDDLEWARE_PATH}" to your MIDDLEWARE list.'
            )

    # 3) SHIPEASY = {...} config block (append at end of file)
    if not _has_shipeasy_block(new):
        new = ensure_os_import(new)
        if not new.endswith("\n"):
            new += "\n"
        new += "\n" + SHIPEASY_BLOCK
        changed.append("appended the SHIPEASY = {...} config block")

    return new, changed, manual


def env_has_key(text: str, key: str = ENV_KEY) -> bool:
    return bool(re.search(rf"^{re.escape(key)}=", text, re.MULTILINE))


def ensure_env_key(text: str, key: str = ENV_KEY) -> Tuple[str, bool]:
    """Append ``KEY=`` to an env file's text if absent.

    Returns ``(new_text, changed)``. Idempotent — a second call is a no-op.
    """
    if env_has_key(text, key):
        return text, False
    suffix = "" if text == "" or text.endswith("\n") else "\n"
    return f"{text}{suffix}{key}=\n", True


# --------------------------------------------------------------------------- #
# Settings-file discovery.                                                      #
# --------------------------------------------------------------------------- #


def settings_path_from_module(settings_module: Optional[str], base_dir: Optional[Path] = None) -> Optional[Path]:
    """Resolve a ``DJANGO_SETTINGS_MODULE`` dotted name to a file path.

    Pure helper (no import side effects): turns ``"myproject.settings"`` into
    ``myproject/settings.py`` under ``base_dir`` (cwd by default) if that file
    exists.
    """
    if not settings_module:
        return None
    base = Path(base_dir) if base_dir is not None else Path.cwd()
    rel = Path(*settings_module.split(".")).with_suffix(".py")
    candidate = base / rel
    return candidate if candidate.is_file() else None


# --------------------------------------------------------------------------- #
# The Django management command.                                                #
# --------------------------------------------------------------------------- #


class Command(BaseCommand):
    help = (
        "Wire Shipeasy into this Django project: add 'shipeasy.django' to "
        "INSTALLED_APPS, the anon-id middleware to MIDDLEWARE, and a SHIPEASY "
        "config block to settings (idempotent)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--settings-file",
            dest="settings_file",
            default=None,
            help="Path to the settings file to patch "
            "(default: auto-detect from DJANGO_SETTINGS_MODULE).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-apply edits even if some appear present (still idempotent "
            "per-edit; never duplicates).",
        )
        parser.add_argument(
            "--no-env",
            action="store_true",
            help="Do not touch .env / .env.example.",
        )

    # -- helpers that need Django/settings context ------------------------- #

    def _resolve_settings_file(self, explicit: Optional[str]) -> Path:
        if explicit:
            p = Path(explicit)
            if not p.is_file():
                raise CommandError(f"--settings-file not found: {p}")
            return p

        module = os.environ.get("DJANGO_SETTINGS_MODULE")
        p = settings_path_from_module(module)
        if p is None:
            raise CommandError(
                "Could not auto-detect the settings file from "
                f"DJANGO_SETTINGS_MODULE={module!r}. Pass --settings-file PATH."
            )
        return p

    def _patch_env_files(self, project_dir: Path) -> None:
        for name in (".env", ".env.example"):
            path = project_dir / name
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            new, changed = ensure_env_key(text)
            if changed:
                path.write_text(new, encoding="utf-8")
                self.stdout.write(self.style.SUCCESS(f"  + {ENV_KEY}= → {name}"))
            else:
                self.stdout.write(f"  · {name} already has {ENV_KEY}")

    # -- entry point ------------------------------------------------------- #

    def handle(self, *args, **options) -> None:
        settings_file = self._resolve_settings_file(options.get("settings_file"))
        original = settings_file.read_text(encoding="utf-8")
        new, changed, manual = patch_settings(original)

        if new != original:
            settings_file.write_text(new, encoding="utf-8")

        self.stdout.write(self.style.MIGRATE_HEADING(f"Shipeasy → {settings_file}"))
        if changed:
            for c in changed:
                self.stdout.write(self.style.SUCCESS(f"  + {c}"))
        else:
            self.stdout.write("  · settings already wired (nothing to do)")

        if manual:
            self.stdout.write(
                self.style.WARNING(
                    "\n  Could not auto-edit some settings — add these by hand:"
                )
            )
            for m in manual:
                self.stdout.write(f"    - {m}")
            self.stdout.write("\n  SHIPEASY config block:\n")
            self.stdout.write(SHIPEASY_BLOCK)

        if not options.get("no_env"):
            self.stdout.write("")
            self._patch_env_files(settings_file.parent)
            # Also check the project root (one dir up from settings package),
            # where .env commonly lives.
            self._patch_env_files(settings_file.parent.parent)

        self._print_next_steps()

    def _print_next_steps(self) -> None:
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Next steps:"))
        self.stdout.write(
            "  1. Mint a SERVER key: https://app.shipeasy.ai → Settings → SDK keys"
        )
        self.stdout.write(
            f"  2. Set {ENV_KEY} in your environment (or .env)."
        )
        self.stdout.write(
            "  3. (logged-out bucketing) the AnonIdMiddleware mints the shared "
            "__se_anon_id cookie automatically."
        )
        self.stdout.write("")
        self.stdout.write("  Read a flag anywhere, per request:")
        self.stdout.write(
            '    shipeasy.Client(request.user).get_flag("new_checkout")'
        )
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("  Docs: https://docs.shipeasy.ai"))
