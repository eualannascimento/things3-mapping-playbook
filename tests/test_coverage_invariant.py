"""Reconcile the playbook, the ledger and the tests. This is the gate.

The project's stated rule is that a capability claim needs a live test. Before
this test existed, that was a policy in a document; now a claim without a test
fails the build.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from things3.verification import ledger, recipes

LIVE_TESTS = Path(__file__).parent / "live"

#: The recipes still waiting for a test. This number may only ever go DOWN.
#: Raising it means a claim was added without a test, which is the thing this
#: file exists to prevent.
#:
#: Set this to whatever `len(ledger.load().pending)` reports after the live run
#: in Task 4 -- 67 if THINGS_AUTH_TOKEN was exported, higher if the checklist
#: tests skipped for want of it. Record the number you actually observed; do not
#: copy the one written here.
MAX_PENDING = 69


def _claimed_recipes() -> list[tuple[str, str]]:
    """(recipe id, test file) for every @pytest.mark.verifies in the live suite.

    Parsed rather than collected, so this works with no Things installed.
    """
    claims = []
    for path in LIVE_TESTS.glob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                target = decorator.func
                if (isinstance(target, ast.Attribute) and target.attr == "verifies"
                        and decorator.args):
                    claims.append((ast.literal_eval(decorator.args[0]), path.name))
    return claims


def test_every_recipe_is_accounted_for():
    """Verified, untestable or pending -- nothing may be simply absent."""
    known = set(recipes.parse())
    current = ledger.load()
    accounted = set(current.recipes) | set(current.untestable) | set(current.pending)
    assert known - accounted == set(), (
        "these recipes are in the playbook but nowhere in the ledger: "
        f"{sorted(known - accounted)}"
    )


def test_the_ledger_claims_nothing_the_playbook_does_not():
    known = set(recipes.parse())
    current = ledger.load()
    accounted = set(current.recipes) | set(current.untestable) | set(current.pending)
    assert accounted - known == set(), (
        "these ledger entries have no playbook recipe -- renamed or removed? "
        f"{sorted(accounted - known)}"
    )


def test_every_test_claims_a_recipe_that_exists():
    known = set(recipes.parse())
    unknown = [(rid, where) for rid, where in _claimed_recipes() if rid not in known]
    assert not unknown, f"tests claiming recipes that do not exist: {unknown}"


def test_no_recipe_is_claimed_by_two_tests():
    seen: dict[str, str] = {}
    clashes = []
    for recipe_id, where in _claimed_recipes():
        if recipe_id in seen:
            clashes.append(f"{recipe_id}: {seen[recipe_id]} and {where}")
        seen[recipe_id] = where
    assert not clashes, "one recipe, one test:\n" + "\n".join(clashes)


def test_a_verified_recipe_is_not_also_pending():
    current = ledger.load()
    both = set(current.recipes) & set(current.pending)
    assert not both, f"verified yet still listed as pending: {sorted(both)}"


def test_untestable_recipes_state_a_reason():
    current = ledger.load()
    empty = [rid for rid, reason in current.untestable.items() if not reason.strip()]
    assert not empty, f"untestable without a reason is just untested: {empty}"


def test_the_pending_list_only_ever_shrinks():
    pending = len(ledger.load().pending)
    assert pending <= MAX_PENDING, (
        f"{pending} recipes pending, ceiling is {MAX_PENDING}. A new claim was added "
        "without a test. Add the test, or lower nothing and reconsider the claim."
    )


def test_no_recipe_is_recorded_as_failing():
    """A failing recipe is a claim the documentation still makes and shouldn't."""
    failing = {rid: entry["test"]
               for rid, entry in ledger.load().recipes.items()
               if entry["status"] == "fail"}
    assert not failing, (
        f"the playbook claims these and the live suite disproves them: {failing}"
    )
