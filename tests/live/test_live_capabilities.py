"""Reproduce the claims in the capability matrix against a real Things install.

Every ✅ and 🟡 in the README asserts something about the platform. Until these
tests existed, a reader had to take that on trust. Now the claims are auditable:
`pytest -m live` either reproduces them or shows which one no longer holds --
which is exactly what would happen if a Things update changed behaviour.
"""
from __future__ import annotations

import pytest

from things3 import applescript, checklist, guards, ops, read, urlscheme

pytestmark = pytest.mark.live


# --- the traps ---------------------------------------------------------------

def test_move_to_project_needs_set_not_move(sandbox, conn):
    """`move ... to` is typed as `list`, so a project destination fails with 301."""
    task, project = sandbox.todo(), sandbox.project()
    sandbox.settle()

    failed = applescript.run(f'  move (to do id "{task}") to project id "{project}"')
    assert not failed.ok and "301" in failed.stderr

    assert ops.move(task, to_project=conn.execute(
        "SELECT title FROM TMTask WHERE uuid=?", (project,)).fetchone()[0]).ok
    sandbox.settle()
    assert conn.execute(
        "SELECT project FROM TMTask WHERE uuid=?", (task,)).fetchone()[0] == project


def test_delete_sends_todo_to_the_trash_and_restore_brings_it_back(sandbox, conn):
    task = sandbox.todo()
    sandbox.settle()

    ops.delete(conn, ops.Kind.TODO, task)
    sandbox.settle()
    assert conn.execute("SELECT trashed FROM TMTask WHERE uuid=?", (task,)).fetchone()[0] == 1

    ops.restore(ops.Kind.TODO, task)
    sandbox.settle()
    assert conn.execute("SELECT trashed FROM TMTask WHERE uuid=?", (task,)).fetchone()[0] == 0


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


# --- checklist: the operation with no direct API ------------------------------

def test_checklist_replacement_preserves_order_and_completed_state(sandbox, conn):
    """The core claim: editing an existing checklist item, losing nothing."""
    pytest.importorskip("os")
    import os
    if not os.environ.get("THINGS_AUTH_TOKEN"):
        pytest.skip("editing an existing checklist needs THINGS_AUTH_TOKEN")

    task = sandbox.todo("checklist")
    sandbox.settle()
    urlscheme.replace_checklist(task, [
        {"title": "first", "completed": False},
        {"title": "typoo", "completed": True},
        {"title": "last", "completed": False},
    ])
    sandbox.settle(2.5)

    plan = checklist.plan(conn, task, rename={"typoo": "typo fixed"})
    checklist.apply(conn, plan)

    after = read.checklist_items(conn, task)
    assert [i["title"] for i in after] == ["first", "typo fixed", "last"], "order must survive"
    assert after[1]["status"] == read.STATUS_COMPLETED, "checked state must survive"
    assert plan.backup_path and plan.backup_path.exists(), "a backup must precede the write"


def test_append_checklist_items_does_nothing(sandbox, conn):
    """Documented as working. It is not -- this test exists to catch it changing."""
    import os
    if not os.environ.get("THINGS_AUTH_TOKEN"):
        pytest.skip("needs THINGS_AUTH_TOKEN")

    task = sandbox.todo("append")
    sandbox.settle()
    urlscheme.replace_checklist(task, [{"title": "only", "completed": False}])
    sandbox.settle(2.5)

    urlscheme.send([{"type": "to-do", "operation": "update", "id": task,
                     "attributes": {"append-checklist-items": "should not appear"}}],
                   needs_token=True)
    sandbox.settle(2.5)

    titles = [i["title"] for i in read.checklist_items(conn, task)]
    assert titles == ["only"], (
        "append-checklist-items appears to work now; the docs and the matrix need updating"
    )


# --- headings -----------------------------------------------------------------

def test_heading_is_addressable_as_a_todo_and_can_be_renamed(sandbox, conn):
    """The only route to renaming a heading, and it is not in the dictionary."""
    _project, heading = sandbox.project_with_heading("headproj", "head")

    assert ops.rename(ops.Kind.HEADING, heading, "zzlive-head-renamed").ok
    sandbox.settle()
    assert conn.execute(
        "SELECT title FROM TMTask WHERE uuid=?", (heading,)
    ).fetchone()[0] == "zzlive-head-renamed"


def test_heading_cannot_be_deleted(sandbox, conn):
    """If this ever passes, the matrix has a 🔶 that should become ✅."""
    _project, heading = sandbox.project_with_heading("delproj", "delhead")

    result = applescript.run(f'  delete (to do id "{heading}")')
    assert not result.ok, "heading deletion works now; the matrix needs updating"


# --- guards -------------------------------------------------------------------

def test_recurrence_guard_refuses_a_real_repeating_task(conn):
    """Read-only: finds an existing repeating task and confirms the guard trips."""
    row = conn.execute(
        "SELECT uuid FROM TMTask WHERE rt1_recurrenceRule IS NOT NULL AND trashed=0 LIMIT 1"
    ).fetchone()
    if row is None:
        pytest.skip("no repeating task in this database to test against")

    with pytest.raises(guards.RecurrenceGuardError):
        ops.delete(conn, ops.Kind.TODO, row[0])


def test_verification_catches_a_silent_no_op(sandbox, conn):
    """Moving an area to the Trash returns success and does nothing."""
    name = sandbox.area("silent-noop")
    sandbox.settle()

    result = applescript.run(f'  move (area "{name}") to list "Trash"')
    assert result.ok, "the command itself succeeds"
    exists = conn.execute("SELECT 1 FROM TMArea WHERE title=?", (name,)).fetchone()
    assert exists, "yet the area is still there -- which is why writes get verified"


# --- text integrity -----------------------------------------------------------

def test_accents_and_multiline_notes_survive_a_round_trip(sandbox, conn):
    task = sandbox.todo("text")
    sandbox.settle()
    notes = 'line 1\nline 2 with "quotes"\n   indented\naccents: ção é ã'
    assert applescript.run(
        f'  set notes of to do id "{task}" to "{applescript.escape(notes)}"'
    ).ok
    sandbox.settle()
    assert conn.execute("SELECT notes FROM TMTask WHERE uuid=?", (task,)).fetchone()[0] == notes
