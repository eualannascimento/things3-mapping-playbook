"""Reproduce every heading recipe in the playbook against a real Things install.

Headings are not a class in the AppleScript dictionary, but the object is
addressable as `to do id "<uuid>"`.
"""
from __future__ import annotations

import pytest

from things3 import applescript, ops, read

pytestmark = pytest.mark.live


@pytest.mark.verifies("heading.read", cell="heading/R", grade="🟡")
def test_read_lists_headings_from_sqlite(sandbox, conn):
    _project, heading = sandbox.project_with_heading("read-proj", "read-head")
    sandbox.settle()
    titles = {h["title"] for h in read.headings(conn)}
    assert "zzlive-read-head" in titles


@pytest.mark.verifies("heading.read-one-by-uuid")
def test_read_one_by_uuid_returns_its_name(sandbox, conn):
    _project, heading = sandbox.project_with_heading("read-one-proj", "read-one-head")
    sandbox.settle()
    result = applescript.run(f'  return name of to do id "{heading}"')
    assert result.ok
    assert result.stdout.strip() == "zzlive-read-one-head"


@pytest.mark.verifies("heading.create", cell="heading/C", grade="🟡")
def test_create_only_happens_alongside_the_project(sandbox, conn):
    project, heading = sandbox.project_with_heading("create-proj", "create-head")
    sandbox.settle()
    assert conn.execute(
        "SELECT project FROM TMTask WHERE uuid=?", (heading,)
    ).fetchone()[0] == project


@pytest.mark.verifies("heading.rename", cell="heading/U", grade="🟡")
def test_rename_is_the_only_route_that_works(sandbox, conn):
    """The only route to renaming a heading, and it is not in the dictionary."""
    _project, heading = sandbox.project_with_heading("rename-proj", "rename-head")
    sandbox.settle()
    assert ops.rename(ops.Kind.HEADING, heading, "zzlive-rename-head-after").ok
    sandbox.settle()
    assert conn.execute(
        "SELECT title FROM TMTask WHERE uuid=?", (heading,)
    ).fetchone()[0] == "zzlive-rename-head-after"


@pytest.mark.verifies("heading.edit-status", cell="heading/Done", grade="✅")
def test_edit_status_writes_completed(sandbox, conn):
    _project, heading = sandbox.project_with_heading("status-proj", "status-head")
    sandbox.settle()
    result = applescript.run(f'  set status of to do id "{heading}" to completed')
    assert result.ok
    sandbox.settle()
    assert conn.execute(
        "SELECT status FROM TMTask WHERE uuid=?", (heading,)
    ).fetchone()[0] == read.STATUS_COMPLETED


@pytest.mark.verifies("heading.delete", cell="heading/D", grade="🔶")
def test_delete_has_no_direct_command(sandbox, conn):
    """If this ever passes, the matrix has a 🔶 that should become ✅."""
    _project, heading = sandbox.project_with_heading("delete-proj", "delete-head")
    sandbox.settle()

    via_delete = applescript.run(f'  delete (to do id "{heading}")')
    assert not via_delete.ok, "heading deletion via delete works now; the matrix needs updating"


@pytest.mark.verifies("heading.move-between-projects", cell="heading/Move", grade="🔶")
def test_move_between_projects_runs_but_has_no_effect(sandbox, conn):
    project_a, heading = sandbox.project_with_heading("move-from", "move-head")
    project_b = sandbox.project("move-to")
    sandbox.settle()
    target_title = conn.execute(
        "SELECT title FROM TMTask WHERE uuid=?", (project_b,)
    ).fetchone()[0]

    result = applescript.run(
        f'  set project of to do id "{heading}" to project "{target_title}"'
    )
    assert result.ok, "the command itself succeeds"
    assert conn.execute(
        "SELECT project FROM TMTask WHERE uuid=?", (heading,)
    ).fetchone()[0] == project_a, "yet the heading never actually moved"


@pytest.mark.verifies("heading.duplicate", cell="heading/Dup", grade="🔶")
def test_duplicate_fails_directly_and_must_rebuild_via_the_project(sandbox, conn):
    _project, heading = sandbox.project_with_heading("dup-proj", "dup-head")
    sandbox.settle()

    failed = applescript.run(f'  duplicate (to do id "{heading}")')
    # Different error than the same command on a to-do or project (-1717): a
    # heading is not addressed through its own class, so the failure comes
    # from the underlying `to do id` lookup instead (-10006).
    assert not failed.ok and "-10006" in failed.stderr

    _new_project, copy = sandbox.project_with_heading("dup-proj-2", "dup-head")
    sandbox.settle()
    assert conn.execute(
        "SELECT title FROM TMTask WHERE uuid=?", (copy,)
    ).fetchone()[0] == "zzlive-dup-head"


@pytest.mark.verifies("heading.create-in-an-existing-project")
def test_create_in_an_existing_project_has_no_route(sandbox, conn):
    """Every variation tested must fail or have no effect on an existing project."""
    project = sandbox.project("existing-no-heading")
    sandbox.settle()
    title = conn.execute("SELECT title FROM TMTask WHERE uuid=?", (project,)).fetchone()[0]

    via_make = applescript.run(
        f'  make new to do with properties {{name:"zzlive-fake-head", type:heading}} '
        f'at end of project "{title}"'
    )
    headings_after = [
        h for h in read.headings(conn) if h["project"] == project
    ]
    assert not via_make.ok or not headings_after, (
        "creating a heading in an existing project appears to work now; "
        "the matrix needs updating"
    )
