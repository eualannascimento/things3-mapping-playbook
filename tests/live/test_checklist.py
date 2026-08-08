"""Reproduce every checklist-item recipe in the playbook against a real Things install.

Checklist items are invisible to AppleScript and to the app's experimental JSON
property; SQLite is the only way to read them, and every write is a full-list
replacement through the URL scheme.
"""
from __future__ import annotations

import os

import pytest

from things3 import checklist, read, urlscheme

pytestmark = pytest.mark.live


@pytest.mark.verifies("checklist.read", cell="checklist/R", grade="🟡")
def test_read_orders_items_by_index(sandbox, conn):
    task = sandbox.todo("read")
    sandbox.settle()
    urlscheme.replace_checklist(task, [
        {"title": "first", "completed": False},
        {"title": "second", "completed": True},
    ])
    sandbox.settle(2.5)
    items = read.checklist_items(conn, task)
    assert [i["title"] for i in items] == ["first", "second"]
    assert items[1]["status"] == read.STATUS_COMPLETED


@pytest.mark.verifies("checklist.create-with-the-to-do", cell="checklist/C", grade="✅")
def test_create_with_the_to_do_sends_items_in_the_creation_payload(sandbox, conn):
    result = urlscheme.send([{
        "type": "to-do",
        "attributes": {
            "title": "zzlive-checklist-create",
            "checklist-items": urlscheme.checklist_payload(
                [{"title": "born-with-it", "completed": False}]
            ),
        },
    }])
    sandbox.settle(2.5)
    row = conn.execute(
        "SELECT uuid FROM TMTask WHERE title=?", ("zzlive-checklist-create",)
    ).fetchone()
    assert row is not None
    sandbox.track("to do", row[0])
    items = read.checklist_items(conn, row[0])
    assert [i["title"] for i in items] == ["born-with-it"]


@pytest.mark.verifies("checklist.append-to-an-existing-to-do")
def test_append_checklist_items_does_nothing(sandbox, conn):
    """Documented as working. It is not -- this test exists to catch it changing."""
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


@pytest.mark.verifies("checklist.rename-edit-an-item", cell="checklist/U", grade="🟡")
def test_rename_replaces_the_whole_list_and_preserves_state(sandbox, conn):
    """The core claim: editing an existing checklist item, losing nothing."""
    if not os.environ.get("THINGS_AUTH_TOKEN"):
        pytest.skip("editing an existing checklist needs THINGS_AUTH_TOKEN")

    task = sandbox.todo("rename-item")
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


@pytest.mark.verifies("checklist.delete-an-item", cell="checklist/D", grade="🟡")
def test_delete_an_item_omits_it_from_the_replacement(sandbox, conn):
    if not os.environ.get("THINGS_AUTH_TOKEN"):
        pytest.skip("needs THINGS_AUTH_TOKEN")

    task = sandbox.todo("delete-item")
    sandbox.settle()
    urlscheme.replace_checklist(task, [
        {"title": "keep", "completed": False},
        {"title": "drop", "completed": False},
    ])
    sandbox.settle(2.5)

    plan = checklist.plan(conn, task, remove=["drop"])
    checklist.apply(conn, plan)
    titles = [i["title"] for i in read.checklist_items(conn, task)]
    assert titles == ["keep"]


@pytest.mark.verifies("checklist.move-between-to-dos", cell="checklist/Move", grade="🟡")
def test_move_between_to_dos_replaces_both_sides(sandbox, conn):
    if not os.environ.get("THINGS_AUTH_TOKEN"):
        pytest.skip("needs THINGS_AUTH_TOKEN")

    source, dest = sandbox.todo("move-source"), sandbox.todo("move-dest")
    sandbox.settle()
    urlscheme.replace_checklist(source, [{"title": "movable", "completed": False}])
    sandbox.settle(2.5)

    checklist.move_item(conn, "movable", source, dest, backup_dir=None)
    sandbox.settle(2.5)

    assert [i["title"] for i in read.checklist_items(conn, source)] == []
    assert [i["title"] for i in read.checklist_items(conn, dest)] == ["movable"]


@pytest.mark.verifies("checklist.complete-an-item", cell="checklist/Done", grade="✅")
def test_complete_an_item_sets_completed_true(sandbox, conn):
    if not os.environ.get("THINGS_AUTH_TOKEN"):
        pytest.skip("needs THINGS_AUTH_TOKEN")

    task = sandbox.todo("complete-item")
    sandbox.settle()
    urlscheme.replace_checklist(task, [{"title": "to-check", "completed": False}])
    sandbox.settle(2.5)

    plan = checklist.plan(conn, task)
    plan.after[0]["completed"] = True
    checklist.apply(conn, plan)
    assert read.checklist_items(conn, task)[0]["status"] == read.STATUS_COMPLETED


@pytest.mark.verifies("checklist.limit")
def test_limit_refuses_over_100_items_rather_than_truncating(sandbox, conn):
    task = sandbox.todo("limit")
    sandbox.settle()
    too_many = [{"title": f"item-{i}", "completed": False} for i in range(101)]
    with pytest.raises(ValueError, match="100"):
        urlscheme.replace_checklist(task, too_many)
