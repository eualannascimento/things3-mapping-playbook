"""Library guarantees that are not tied to a single playbook recipe.

These prove behaviour of the guarantee layer itself -- the recurrence guard,
staleness detection, the iteration trap -- rather than a specific capability
claim from the matrix. They carry no @pytest.mark.verifies for that reason.
"""
from __future__ import annotations

import os

import pytest

from things3 import applescript, checklist, guards, ops, read, urlscheme

pytestmark = pytest.mark.live


def test_deleting_while_iterating_the_live_collection_fails(sandbox, conn):
    """Why delete_many() takes a list of uuids instead of running a query."""
    sandbox.todo("iter-a")
    sandbox.todo("iter-b")
    sandbox.settle()

    result = applescript.run(
        '  repeat with t in to dos\n'
        '    if name of t starts with "zzlive-iter" then delete t\n'
        '  end repeat'
    )
    assert not result.ok, "deleting during iteration should fail: it mutates the collection"


def test_recurrence_guard_refuses_a_real_repeating_task(conn):
    """Read-only: finds an existing repeating task and confirms the guard trips."""
    row = conn.execute(
        "SELECT uuid FROM TMTask WHERE rt1_recurrenceRule IS NOT NULL AND trashed=0 LIMIT 1"
    ).fetchone()
    if row is None:
        pytest.skip("no repeating task in this database to test against")

    with pytest.raises(guards.RecurrenceGuardError):
        ops.delete(conn, ops.Kind.TODO, row[0])


def test_stale_plan_is_refused_against_a_real_edit(sandbox, conn):
    """A plan built before someone ticks an item must not clobber that tick."""
    if not os.environ.get("THINGS_AUTH_TOKEN"):
        pytest.skip("needs THINGS_AUTH_TOKEN")

    task = sandbox.todo("stale")
    sandbox.settle()
    urlscheme.replace_checklist(task, [
        {"title": "one", "completed": False},
        {"title": "two", "completed": False},
    ])
    sandbox.settle(2.5)

    plan = checklist.plan(conn, task, rename={"two": "two edited"})

    # meanwhile, the list changes for real
    urlscheme.replace_checklist(task, [
        {"title": "one", "completed": True},
        {"title": "two", "completed": False},
    ])
    sandbox.settle(2.5)

    with pytest.raises(checklist.StaleplanError):
        checklist.apply(conn, plan)

    still_checked = read.checklist_items(conn, task)[0]["status"]
    assert still_checked == read.STATUS_COMPLETED, "the concurrent edit must survive"
