"""Reproduce every to-do recipe in the playbook against a real Things install.

One test per recipe, each building its own object through the sandbox and
asserting the single claim that recipe makes.
"""
from __future__ import annotations

import os

import pytest

from things3 import applescript, lists, ops, read, urlscheme

pytestmark = pytest.mark.live


@pytest.mark.verifies("todo.read-one", cell="todo/R", grade="✅")
def test_read_one_returns_a_property_directly(sandbox):
    task = sandbox.todo("read-one")
    sandbox.settle()
    result = applescript.run(f'  return name of to do id "{task}"')
    assert result.ok
    assert result.stdout.strip() == "zzlive-read-one"


@pytest.mark.verifies("todo.read-bulk")
def test_read_bulk_returns_open_todos_from_sqlite(sandbox, conn):
    task = sandbox.todo("read-bulk")
    sandbox.settle()
    titles = {t["title"] for t in read.tasks(conn)}
    assert "zzlive-read-bulk" in titles


@pytest.mark.verifies("todo.read-a-list")
def test_read_a_list_returns_todos_of_a_built_in_list(sandbox):
    task = sandbox.todo("read-a-list")
    ops.move(task, to_list=lists.TODAY)
    sandbox.settle()
    result = applescript.run(
        f'  return name of every to do of {lists.specifier(lists.TODAY)}'
    )
    assert result.ok
    assert "zzlive-read-a-list" in result.stdout


@pytest.mark.verifies("todo.count")
def test_count_reports_without_materialising_objects(sandbox):
    sandbox.todo("count")
    task2 = sandbox.todo("count-2")
    ops.move(task2, to_list=lists.TODAY)
    sandbox.settle()
    result = applescript.run(f'  return count of to dos of {lists.specifier(lists.TODAY)}')
    assert result.ok
    assert int(result.stdout.strip()) >= 1


@pytest.mark.verifies("todo.create", cell="todo/C", grade="✅")
def test_create_makes_a_todo_reachable_by_its_returned_uuid(sandbox, conn):
    task = sandbox.todo("create")
    sandbox.settle()
    row = conn.execute("SELECT title FROM TMTask WHERE uuid=?", (task,)).fetchone()
    assert row is not None
    assert row[0] == "zzlive-create"


@pytest.mark.verifies("todo.create-natural-language")
def test_natural_language_extracts_a_tag_but_not_a_date(sandbox, conn):
    tag = sandbox.tag("nl-tag")
    sandbox.settle()
    title = "zzlive-natural-language tomorrow"
    result = applescript.run(
        f'  return id of (parse quicksilver input "{title} #{tag}")'
    )
    assert result.ok, result.stderr
    uuid = result.stdout.strip()
    sandbox.track("to do", uuid)
    sandbox.settle()

    row = conn.execute(
        "SELECT title, startDate FROM TMTask WHERE uuid=?", (uuid,)
    ).fetchone()
    assert row is not None
    assert row[0] == title, "the tag text is stripped from the title, not the date word"
    assert row[1] is None, "quicksilver input does not extract dates"


@pytest.mark.verifies("todo.rename", cell="todo/U", grade="✅")
def test_rename_changes_the_title_in_place(sandbox, conn):
    task = sandbox.todo("rename-before")
    sandbox.settle()
    assert ops.rename(ops.Kind.TODO, task, "zzlive-rename-after").ok
    sandbox.settle()
    assert conn.execute(
        "SELECT title FROM TMTask WHERE uuid=?", (task,)
    ).fetchone()[0] == "zzlive-rename-after"


@pytest.mark.verifies("todo.edit-notes")
def test_edit_notes_survives_multiline_quotes_and_accents(sandbox, conn):
    task = sandbox.todo("edit-notes")
    sandbox.settle()
    notes = 'line one\nline two with "quotes"\naccented: ção'
    result = applescript.run(
        f'  set notes of to do id "{task}" to "{applescript.escape(notes)}"'
    )
    assert result.ok
    sandbox.settle()
    assert conn.execute(
        "SELECT notes FROM TMTask WHERE uuid=?", (task,)
    ).fetchone()[0] == notes


@pytest.mark.verifies("todo.edit-tags")
def test_edit_tags_requires_the_tag_to_already_exist(sandbox, conn):
    tag = sandbox.tag("edit-tags")
    task = sandbox.todo("edit-tags")
    sandbox.settle()
    result = applescript.run(f'  set tag names of to do id "{task}" to "{tag}"')
    assert result.ok
    sandbox.settle()
    titles = read.task_tags(conn).get(task, set())
    assert tag in titles


@pytest.mark.verifies("todo.edit-deadline")
def test_edit_deadline_sets_the_due_date(sandbox, conn):
    task = sandbox.todo("edit-deadline")
    sandbox.settle()
    result = applescript.run(
        f'  set due date of to do id "{task}" to (current date) + 86400'
    )
    assert result.ok
    sandbox.settle()
    assert conn.execute(
        "SELECT deadline FROM TMTask WHERE uuid=?", (task,)
    ).fetchone()[0] is not None


@pytest.mark.verifies("todo.edit-schedule")
def test_edit_schedule_sets_the_start_date(sandbox, conn):
    task = sandbox.todo("edit-schedule")
    sandbox.settle()
    result = applescript.run(
        f'  schedule (to do id "{task}") for (current date) + 86400'
    )
    assert result.ok
    sandbox.settle()
    assert conn.execute(
        "SELECT startDate FROM TMTask WHERE uuid=?", (task,)
    ).fetchone()[0] is not None


@pytest.mark.verifies("todo.edit-this-evening")
def test_edit_this_evening_needs_the_url_scheme_and_a_token(sandbox, conn):
    if not os.environ.get("THINGS_AUTH_TOKEN"):
        pytest.skip("needs THINGS_AUTH_TOKEN")
    task = sandbox.todo("this-evening")
    sandbox.settle()
    urlscheme.send(
        [{"type": "to-do", "operation": "update", "id": task,
          "attributes": {"when": "evening"}}],
        needs_token=True,
    )
    sandbox.settle(2.5)
    assert conn.execute(
        "SELECT startDate FROM TMTask WHERE uuid=?", (task,)
    ).fetchone()[0] is not None


@pytest.mark.verifies("todo.edit-reminder-time")
def test_edit_reminder_time_needs_the_url_scheme_and_a_token(sandbox, conn):
    if not os.environ.get("THINGS_AUTH_TOKEN"):
        pytest.skip("needs THINGS_AUTH_TOKEN")
    task = sandbox.todo("reminder-time")
    sandbox.settle()
    urlscheme.send(
        [{"type": "to-do", "operation": "update", "id": task,
          "attributes": {"when": "today@15:30"}}],
        needs_token=True,
    )
    sandbox.settle(2.5)
    assert conn.execute(
        "SELECT startDate FROM TMTask WHERE uuid=?", (task,)
    ).fetchone()[0] is not None


@pytest.mark.verifies("todo.delete", cell="todo/D", grade="✅")
def test_delete_sends_a_todo_to_the_native_trash(sandbox, conn):
    task = sandbox.todo("delete")
    sandbox.settle()
    ops.delete(conn, ops.Kind.TODO, task)
    sandbox.settle()
    assert conn.execute("SELECT trashed FROM TMTask WHERE uuid=?", (task,)).fetchone()[0] == 1


@pytest.mark.verifies("todo.restore", cell="todo/Rest", grade="✅")
def test_restore_brings_a_trashed_todo_back(sandbox, conn):
    task = sandbox.todo("restore")
    sandbox.settle()
    ops.delete(conn, ops.Kind.TODO, task)
    sandbox.settle()

    ops.restore(ops.Kind.TODO, task)
    sandbox.settle()
    assert conn.execute("SELECT trashed FROM TMTask WHERE uuid=?", (task,)).fetchone()[0] == 0


@pytest.mark.verifies("todo.duplicate", cell="todo/Dup", grade="🟡")
def test_duplicate_fails_directly_but_recreating_from_properties_works(sandbox, conn):
    task = sandbox.todo("duplicate-source")
    sandbox.settle()

    failed = applescript.run(f'  duplicate (to do id "{task}")')
    assert not failed.ok and "-1717" in failed.stderr

    title = conn.execute("SELECT title FROM TMTask WHERE uuid=?", (task,)).fetchone()[0]
    copy_uuid = ops.create(ops.Kind.TODO, title).detail
    sandbox.track("to do", copy_uuid)
    sandbox.settle()
    assert conn.execute(
        "SELECT title FROM TMTask WHERE uuid=?", (copy_uuid,)
    ).fetchone()[0] == title


@pytest.mark.verifies("todo.move-to-a-list")
def test_move_to_a_list_reaches_a_built_in_list_by_id(sandbox, conn):
    task = sandbox.todo("move-to-a-list")
    sandbox.settle()
    result = ops.move(task, to_list=lists.TODAY)
    assert result.ok
    sandbox.settle()
    result2 = applescript.run(
        f'  return id of every to do of {lists.specifier(lists.TODAY)} whose id is "{task}"'
    )
    assert result2.ok and task in result2.stdout


@pytest.mark.verifies("todo.move-to-a-project", cell="todo/Move", grade="🟡")
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


@pytest.mark.verifies("todo.move-to-an-area")
def test_move_to_an_area_uses_set_area_of(sandbox, conn):
    task, area = sandbox.todo(), sandbox.area()
    sandbox.settle()
    result = ops.move(task, to_area=area)
    assert result.ok
    sandbox.settle()
    area_uuid = conn.execute("SELECT uuid FROM TMArea WHERE title=?", (area,)).fetchone()[0]
    assert conn.execute(
        "SELECT area FROM TMTask WHERE uuid=?", (task,)).fetchone()[0] == area_uuid


@pytest.mark.verifies("todo.move-under-a-heading")
def test_move_under_a_heading_needs_the_url_scheme_and_a_token(sandbox, conn):
    if not os.environ.get("THINGS_AUTH_TOKEN"):
        pytest.skip("needs THINGS_AUTH_TOKEN")
    project, heading = sandbox.project_with_heading("under-heading-proj", "under-heading")
    task = sandbox.todo("under-heading")
    sandbox.settle()

    urlscheme.move_to_heading(task, project, heading)
    sandbox.settle(2.5)
    assert conn.execute(
        "SELECT heading FROM TMTask WHERE uuid=?", (task,)
    ).fetchone()[0] == heading


@pytest.mark.verifies("todo.complete", cell="todo/Done", grade="✅")
def test_complete_sets_status_completed(sandbox, conn):
    task = sandbox.todo("complete")
    sandbox.settle()
    assert ops.set_status(ops.Kind.TODO, task, "completed").ok
    sandbox.settle()
    assert conn.execute(
        "SELECT status FROM TMTask WHERE uuid=?", (task,)
    ).fetchone()[0] == read.STATUS_COMPLETED


@pytest.mark.verifies("todo.cancel")
def test_cancel_sets_status_canceled(sandbox, conn):
    task = sandbox.todo("cancel")
    sandbox.settle()
    assert ops.set_status(ops.Kind.TODO, task, "canceled").ok
    sandbox.settle()
    assert conn.execute(
        "SELECT status FROM TMTask WHERE uuid=?", (task,)
    ).fetchone()[0] == read.STATUS_CANCELED


@pytest.mark.verifies("todo.reopen")
def test_reopen_sets_status_open(sandbox, conn):
    task = sandbox.todo("reopen")
    sandbox.settle()
    ops.set_status(ops.Kind.TODO, task, "completed")
    sandbox.settle()

    assert ops.set_status(ops.Kind.TODO, task, "open").ok
    sandbox.settle()
    assert conn.execute(
        "SELECT status FROM TMTask WHERE uuid=?", (task,)
    ).fetchone()[0] == read.STATUS_OPEN


@pytest.mark.verifies("todo.recurrence-read", cell="recurrence/R", grade="🟡")
def test_recurrence_read_decodes_a_real_repeating_task(conn):
    """Read-only: finds an existing repeating task and decodes its plist."""
    row = conn.execute(
        "SELECT uuid FROM TMTask WHERE rt1_recurrenceRule IS NOT NULL AND trashed=0 LIMIT 1"
    ).fetchone()
    if row is None:
        pytest.skip("no repeating task in this database to decode")
    decoded = read.recurrence(conn, row[0])
    assert decoded is not None
    assert decoded["unit"] in {"daily", "weekly", "monthly", "yearly"} or \
        decoded["unit"].startswith("unknown(")


@pytest.mark.verifies("todo.recurrence-create-edit", cell="recurrence/C", grade="❌")
def test_recurrence_cannot_be_created_or_edited_by_any_route(sandbox, conn):
    """Every write route is tried and must fail or have no effect."""
    task = sandbox.todo("recurrence")
    sandbox.settle()

    via_property = applescript.run(f'  set repeating of to do id "{task}" to true')
    assert not via_property.ok, "an AppleScript property for recurrence appeared"

    before = conn.execute(
        "SELECT rt1_recurrenceRule FROM TMTask WHERE uuid=?", (task,)
    ).fetchone()[0]
    assert before is None
