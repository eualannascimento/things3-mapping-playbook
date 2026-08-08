"""Generate the capability matrix from the ledger.

Hand-written, the matrix could claim something no test supports -- which is how
this project ended up with 78 documented recipes and seven tests. Generated, a
cell can only carry a grade that a passing test put there.
"""
from __future__ import annotations

import re

from .ledger import Ledger

ROWS = [("todo", "To-do"), ("project", "Project"), ("area", "Area"),
        ("tag", "Tag"), ("heading", "Heading"),
        ("checklist", "Checklist item"), ("recurrence", "Recurrence")]

COLUMNS = ["C", "R", "U", "D", "Dup", "Move", "Done", "Rest"]

#: Cells the platform has no concept of -- not gaps, just inapplicable.
NOT_APPLICABLE = {
    "area/Move", "area/Done", "tag/Done", "heading/Rest", "checklist/Rest",
    "recurrence/Dup", "recurrence/Move", "recurrence/Done", "recurrence/Rest",
}

UNTESTED = "·"


class CellConflictError(ValueError):
    """Two passing recipes grade the same cell differently."""


def _grades(ledger: Ledger) -> dict[str, str]:
    grades: dict[str, tuple[str, str]] = {}
    for recipe_id, entry in ledger.recipes.items():
        cell, grade = entry.get("cell"), entry.get("grade")
        if not cell or not grade or entry["status"] != "pass":
            continue
        if cell in grades and grades[cell][0] != grade:
            raise CellConflictError(
                f"{cell} is graded {grades[cell][0]} by {grades[cell][1]} and "
                f"{grade} by {recipe_id}; one of them is wrong"
            )
        grades[cell] = (grade, recipe_id)
    return {cell: grade for cell, (grade, _) in grades.items()}


def matrix(ledger: Ledger) -> str:
    grades = _grades(ledger)
    lines = ["| | " + " | ".join(COLUMNS) + " |",
             "|---|" + ":-:|" * len(COLUMNS)]
    for slug, label in ROWS:
        cells = []
        for column in COLUMNS:
            key = f"{slug}/{column}"
            if key in NOT_APPLICABLE:
                cells.append("➖")
            else:
                cells.append(grades.get(key, UNTESTED))
        lines.append(f"| **{label}** | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def apply(text: str, block: str, name: str) -> str:
    """Replace the content between <!-- generated:name --> markers.

    Matches even when the block is currently empty -- the opening marker
    directly followed by the closing one, as it is right after Task 6 wraps the
    README for the first time.
    """
    pattern = re.compile(
        rf"<!-- generated:{name} -->\n.*?<!-- /generated:{name} -->",
        re.DOTALL,
    )
    if not pattern.search(text):
        raise ValueError(f"no <!-- generated:{name} --> block found")
    replacement = f"<!-- generated:{name} -->\n{block}\n<!-- /generated:{name} -->"
    return pattern.sub(lambda _: replacement, text)
