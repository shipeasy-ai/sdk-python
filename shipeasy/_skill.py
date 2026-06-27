"""`shipeasy-skill` — install the bundled Shipeasy agent skill into a project.

Python packaging has no safe post-install hook (wheels don't run code; pip runs
non-interactively), so installing the skill is an explicit, opt-in command:

    shipeasy-skill install                 # → .claude/skills/shipeasy-python/SKILL.md
    shipeasy-skill install --dir path/     # custom destination (file or dir)
    shipeasy-skill print                   # write the skill to stdout

The skill (`docs/skill/SKILL.md`) is bundled into the wheel at
`shipeasy/_skill_data/SKILL.md` (see pyproject `force-include`); when running
from a source checkout we fall back to the repo's `docs/skill/SKILL.md`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_DEST = Path(".claude/skills/shipeasy-python/SKILL.md")


def skill_text() -> str:
    """Return the bundled SKILL.md (installed wheel), falling back to the repo
    copy when running from source."""
    try:
        from importlib.resources import files

        res = files("shipeasy").joinpath("_skill_data/SKILL.md")
        if res.is_file():
            return res.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 — any resource lookup failure → dev fallback
        pass
    dev = Path(__file__).resolve().parent.parent / "docs" / "skill" / "SKILL.md"
    return dev.read_text(encoding="utf-8")


def install(dest: Path, force: bool = False) -> int:
    """Copy the skill to ``dest`` (a file, or a directory it's written into)."""
    dest = Path(dest)
    if dest.is_dir() or dest.suffix == "":
        dest = dest / "SKILL.md"
    if dest.exists() and not force:
        print(
            f"shipeasy-skill: refusing to overwrite {dest} — pass --force",
            file=sys.stderr,
        )
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(skill_text(), encoding="utf-8")
    print(f"shipeasy-skill: installed the Shipeasy agent skill → {dest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shipeasy-skill",
        description="Install the Shipeasy Python agent skill into your project.",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_install = sub.add_parser(
        "install", help="copy SKILL.md into your agent skills directory"
    )
    p_install.add_argument(
        "--dir",
        default=str(DEFAULT_DEST),
        help=f"destination file or directory (default: {DEFAULT_DEST})",
    )
    p_install.add_argument(
        "--force", action="store_true", help="overwrite an existing file"
    )

    sub.add_parser("print", help="print the skill to stdout")

    args = parser.parse_args(argv)
    if args.cmd == "install":
        return install(Path(args.dir), args.force)
    if args.cmd == "print":
        print(skill_text())
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
