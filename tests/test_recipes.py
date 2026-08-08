"""The playbook is the single source of what this project claims."""
from pathlib import Path

import pytest

from things3.verification import recipes


@pytest.fixture
def playbook(tmp_path) -> Path:
    path = tmp_path / "PLAYBOOK.md"
    path.write_text(
        "# Playbook\n\n"
        "## Notation\n\n"
        "| | Meaning |\n|---|---|\n| `AS:` | AppleScript |\n\n"
        "## To-do\n\n"
        "| Action | Recipe |\n|---|---|\n"
        '| **Read** (one) | `AS: return name of to do id "<uuid>"` |\n'
        "| **Delete** | `AS: move to the Trash` |\n\n"
        "## Checklist item\n\n"
        "| Action | Recipe |\n|---|---|\n"
        "| **Limit** | 100 items per to-do |\n",
        encoding="utf-8",
    )
    return path


def test_ids_combine_section_and_action(playbook):
    assert list(recipes.parse(playbook)) == [
        "todo.read-one", "todo.delete", "checklist.limit"
    ]


def test_the_action_text_is_kept_for_reporting(playbook):
    assert recipes.parse(playbook)["todo.read-one"] == "Read (one)"


def test_rows_outside_a_known_section_are_ignored(playbook):
    """The Notation table is documentation, not a claim."""
    assert not any(rid.startswith("notation") for rid in recipes.parse(playbook))


def test_duplicate_ids_are_refused(tmp_path):
    path = tmp_path / "P.md"
    path.write_text(
        "## Tag\n\n| Action | Recipe |\n|---|---|\n"
        "| **Create** | `AS: a` |\n| **Create** | `AS: b` |\n",
        encoding="utf-8",
    )
    with pytest.raises(recipes.DuplicateRecipeError, match="tag.create"):
        recipes.parse(path)


def test_the_real_playbook_parses_to_unique_ids():
    parsed = recipes.parse(recipes.PLAYBOOK)
    assert len(parsed) == 78, f"the playbook now claims {len(parsed)} recipes"
    assert "todo.delete" in parsed
    assert "app.empty-the-trash" in parsed
