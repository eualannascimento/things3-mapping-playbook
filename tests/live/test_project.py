"""Reproduce every project recipe in the playbook against a real Things install."""
from __future__ import annotations

import pytest

from things3 import applescript, lists, ops, read

pytestmark = pytest.mark.live


@pytest.mark.verifies("project.read", cell="project/R", grade="✅")
def test_read_returns_the_project_name(sandbox):
    project = sandbox.project("read")
    sandbox.settle()
    result = applescript.run(f'  return name of project id "{project}"')
    assert result.ok
    assert result.stdout.strip() == "zzlive-read"


@pytest.mark.verifies("project.read-its-to-dos")
def test_read_its_to_dos_lists_todos_inside_the_project(sandbox, conn):
    project = sandbox.project("with-todos")
    task = sandbox.todo("inside-project")
    ops.move(task, to_project=conn.execute(
        "SELECT title FROM TMTask WHERE uuid=?", (project,)).fetchone()[0])
    sandbox.settle()
    result = applescript.run(f'  return name of every to do of project id "{project}"')
    assert result.ok
    assert "zzlive-inside-project" in result.stdout


@pytest.mark.verifies("project.create", cell="project/C", grade="✅")
def test_create_makes_a_project_reachable_by_its_returned_uuid(sandbox, conn):
    project = sandbox.project("create")
    sandbox.settle()
    row = conn.execute("SELECT title FROM TMTask WHERE uuid=?", (project,)).fetchone()
    assert row is not None and row[0] == "zzlive-create"


@pytest.mark.verifies("project.create-with-headings", cell="heading/C", grade="🟡")
def test_create_with_headings_is_the_only_way_to_have_headings(sandbox, conn):
    project, heading = sandbox.project_with_heading("with-headings", "only-heading")
    sandbox.settle()
    row = conn.execute(
        "SELECT project FROM TMTask WHERE uuid=?", (heading,)
    ).fetchone()
    assert row is not None and row[0] == project


@pytest.mark.verifies("project.rename", cell="project/U", grade="✅")
def test_rename_changes_the_title_in_place(sandbox, conn):
    project = sandbox.project("rename-before")
    sandbox.settle()
    assert ops.rename(ops.Kind.PROJECT, "zzlive-rename-before", "zzlive-rename-after",
                      by_id=False).ok
    sandbox.settle()
    assert conn.execute(
        "SELECT title FROM TMTask WHERE uuid=?", (project,)
    ).fetchone()[0] == "zzlive-rename-after"


@pytest.mark.verifies("project.edit-notes")
def test_edit_notes_sets_the_notes_field(sandbox, conn):
    project = sandbox.project("edit-notes")
    sandbox.settle()
    result = applescript.run(
        '  set notes of project "zzlive-edit-notes" to "some notes"'
    )
    assert result.ok
    sandbox.settle()
    assert conn.execute(
        "SELECT notes FROM TMTask WHERE uuid=?", (project,)
    ).fetchone()[0] == "some notes"


@pytest.mark.verifies("project.delete", cell="project/D", grade="✅")
def test_delete_sends_a_project_to_the_native_trash(sandbox, conn):
    project = sandbox.project("delete")
    sandbox.settle()
    ops.delete(conn, ops.Kind.PROJECT, project)
    sandbox.settle()
    assert conn.execute(
        "SELECT trashed FROM TMTask WHERE uuid=?", (project,)
    ).fetchone()[0] == 1


@pytest.mark.verifies("project.restore", cell="project/Rest", grade="✅")
def test_restore_brings_a_trashed_project_back(sandbox, conn):
    project = sandbox.project("restore")
    sandbox.settle()
    ops.delete(conn, ops.Kind.PROJECT, project)
    sandbox.settle()

    ops.restore(ops.Kind.PROJECT, project)
    sandbox.settle()
    assert conn.execute(
        "SELECT trashed FROM TMTask WHERE uuid=?", (project,)
    ).fetchone()[0] == 0


@pytest.mark.verifies("project.duplicate", cell="project/Dup", grade="🟡")
def test_duplicate_is_read_properties_then_recreate(sandbox, conn):
    project = sandbox.project("duplicate-source")
    sandbox.settle()
    title = conn.execute("SELECT title FROM TMTask WHERE uuid=?", (project,)).fetchone()[0]

    copy_uuid = ops.create(ops.Kind.PROJECT, title).detail
    sandbox.track("project", copy_uuid)
    sandbox.settle()
    assert conn.execute(
        "SELECT title FROM TMTask WHERE uuid=?", (copy_uuid,)
    ).fetchone()[0] == title


@pytest.mark.verifies("project.move-to-an-area", cell="project/Move", grade="✅")
def test_move_to_an_area_uses_set_area_of(sandbox, conn):
    project, area = sandbox.project("move-to-area"), sandbox.area()
    sandbox.settle()
    result = applescript.run(
        f'  set area of project "zzlive-move-to-area" to area "{area}"'
    )
    assert result.ok
    sandbox.settle()
    area_uuid = conn.execute("SELECT uuid FROM TMArea WHERE title=?", (area,)).fetchone()[0]
    assert conn.execute(
        "SELECT area FROM TMTask WHERE uuid=?", (project,)
    ).fetchone()[0] == area_uuid


@pytest.mark.verifies("project.complete", cell="project/Done", grade="✅")
def test_complete_sets_status_completed(sandbox, conn):
    project = sandbox.project("complete")
    sandbox.settle()
    result = applescript.run('  set status of project "zzlive-complete" to completed')
    assert result.ok
    sandbox.settle()
    assert conn.execute(
        "SELECT status FROM TMTask WHERE uuid=?", (project,)
    ).fetchone()[0] == read.STATUS_COMPLETED


@pytest.mark.verifies("project.add-a-heading-after-creation", cell="heading/Move", grade="🔶")
def test_add_a_heading_after_creation_needs_a_new_project(sandbox, conn):
    """No command adds a heading in place -- rebuild via a new project instead."""
    old_project = sandbox.project("no-heading-yet")
    task = sandbox.todo("to-move")
    old_title = conn.execute(
        "SELECT title FROM TMTask WHERE uuid=?", (old_project,)
    ).fetchone()[0]
    ops.move(task, to_project=old_title)
    sandbox.settle()

    new_project, heading = sandbox.project_with_heading(
        "with-heading-after", "added-after"
    )
    ops.move(task, to_project=conn.execute(
        "SELECT title FROM TMTask WHERE uuid=?", (new_project,)).fetchone()[0])
    sandbox.settle()

    assert conn.execute(
        "SELECT project FROM TMTask WHERE uuid=?", (task,)
    ).fetchone()[0] == new_project
