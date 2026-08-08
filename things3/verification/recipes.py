"""Turn the playbook into a set of recipe ids.

The id is derived from the document rather than written into it, so there is no
second registry to fall out of sync. Rename an action and its id changes, which
breaks the test that claims it -- loudly, which is the point.
"""
from __future__ import annotations

import re
from pathlib import Path

PLAYBOOK = Path(__file__).resolve().parents[2] / "docs" / "PLAYBOOK.md"

#: Only these sections hold capability claims. Anything else is prose.
SECTION_SLUGS = {
    "To-do": "todo",
    "Project": "project",
    "Area": "area",
    "Tag": "tag",
    "Heading": "heading",
    "Checklist item": "checklist",
    "Application": "app",
}

_SECTION = re.compile(r"^##\s+(.*?)\s*$")


class DuplicateRecipeError(ValueError):
    """Two rows produced the same id, so one of them could never be tested."""


def _slug(text: str) -> str:
    text = re.sub(r"[*`]", "", text).strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def parse(path: Path | None = None) -> dict[str, str]:
    """Map recipe id -> action text, in document order."""
    path = path or PLAYBOOK
    section: str | None = None
    found: dict[str, str] = {}

    for line in path.read_text(encoding="utf-8").splitlines():
        heading = _SECTION.match(line)
        if heading:
            section = SECTION_SLUGS.get(heading.group(1))
            continue
        if section is None or not line.startswith("| **"):
            continue

        action = re.sub(r"[*`]", "", line.split("|")[1]).strip()
        recipe_id = f"{section}.{_slug(action)}"
        if recipe_id in found:
            raise DuplicateRecipeError(
                f"{recipe_id} appears twice in {path.name}; "
                "two rows with the same action cannot be validated separately"
            )
        found[recipe_id] = action

    return found
