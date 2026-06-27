"""Tests for the `shipeasy-skill` installer (shipeasy/_skill.py)."""
from pathlib import Path

from shipeasy import _skill


def test_skill_text_has_frontmatter():
    text = _skill.skill_text()
    assert text.startswith("---")
    assert "name: shipeasy-python" in text


def test_install_into_directory(tmp_path: Path):
    rc = _skill.install(tmp_path / ".claude/skills/shipeasy-python")
    dest = tmp_path / ".claude/skills/shipeasy-python/SKILL.md"
    assert rc == 0
    assert dest.is_file()
    assert dest.read_text().startswith("---")


def test_install_to_explicit_file(tmp_path: Path):
    dest = tmp_path / "nested/SKILL.md"
    assert _skill.install(dest) == 0
    assert dest.read_text() == _skill.skill_text()


def test_refuses_overwrite_without_force(tmp_path: Path):
    dest = tmp_path / "SKILL.md"
    assert _skill.install(dest) == 0
    assert _skill.install(dest) == 1  # exists → refuse
    assert _skill.install(dest, force=True) == 0  # force → overwrite


def test_main_install_and_print(tmp_path: Path, capsys):
    assert _skill.main(["install", "--dir", str(tmp_path), "--force"]) == 0
    assert (tmp_path / "SKILL.md").is_file()
    assert _skill.main(["print"]) == 0
    out = capsys.readouterr().out
    assert "name: shipeasy-python" in out
