"""The matrix is generated, so a claim cannot outlive the test behind it."""
import pytest

from things3.verification import ledger, render


def _ledger(cells: dict[str, str]) -> ledger.Ledger:
    """A ledger whose only content is cell -> grade, one recipe per cell."""
    return ledger.Ledger(recipes={
        f"r{n}": {"status": "pass", "test": "t", "cell": cell, "grade": grade,
                  "first_verified": "2026-08-07", "last_verified": "2026-08-07"}
        for n, (cell, grade) in enumerate(cells.items())
    })


def test_a_graded_cell_appears_in_the_table():
    table = render.matrix(_ledger({"todo/D": "✅"}))
    row = next(line for line in table.splitlines() if "To-do" in line)
    assert "✅" in row


def test_an_ungraded_cell_renders_as_untested():
    table = render.matrix(ledger.Ledger())
    assert "·" in table, "cells with no passing test must be visibly untested"


def test_two_recipes_grading_one_cell_differently_is_an_error():
    conflicting = _ledger({"todo/D": "✅"})
    conflicting.recipes["other"] = {"status": "pass", "test": "t2",
                                    "cell": "todo/D", "grade": "🟡",
                                    "first_verified": None, "last_verified": "x"}
    with pytest.raises(render.CellConflictError, match="todo/D"):
        render.matrix(conflicting)


def test_a_failing_recipe_does_not_grade_its_cell():
    failed = _ledger({"todo/D": "✅"})
    failed.recipes["r0"]["status"] = "fail"
    table = render.matrix(failed)
    row = next(line for line in table.splitlines() if "To-do" in line)
    assert "✅" not in row


def test_apply_replaces_only_the_marked_block():
    text = ("before\n<!-- generated:matrix -->\nold\n<!-- /generated:matrix -->\nafter\n")
    result = render.apply(text, "new", "matrix")
    assert "old" not in result
    assert result.startswith("before") and result.rstrip().endswith("after")


def test_apply_refuses_when_the_markers_are_missing():
    with pytest.raises(ValueError, match="matrix"):
        render.apply("no markers here", "new", "matrix")
