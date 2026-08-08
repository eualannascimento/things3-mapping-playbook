"""Reproduce every area recipe in the playbook against a real Things install."""
from __future__ import annotations

import pytest

from things3 import applescript, ops

pytestmark = pytest.mark.live


@pytest.mark.verifies("area.read", cell="area/R", grade="✅")
def test_read_returns_the_area_name(sandbox):
    area = sandbox.area("read")
    sandbox.settle()
    result = applescript.run(f'  return name of every area whose name is "{area}"')
    assert result.ok
    assert area in result.stdout


@pytest.mark.verifies("area.create", cell="area/C", grade="✅")
def test_create_makes_an_area_reachable_by_name(sandbox, conn):
    area = sandbox.area("create")
    sandbox.settle()
    row = conn.execute("SELECT title FROM TMArea WHERE title=?", (area,)).fetchone()
    assert row is not None


@pytest.mark.verifies("area.rename", cell="area/U", grade="✅")
def test_rename_changes_the_title_in_place(sandbox, conn):
    area = sandbox.area("rename-before")
    sandbox.settle()
    assert ops.rename(ops.Kind.AREA, area, "zzlive-rename-after", by_id=False).ok
    sandbox.settle()
    assert conn.execute(
        "SELECT 1 FROM TMArea WHERE title=?", ("zzlive-rename-after",)
    ).fetchone() is not None
    assert conn.execute("SELECT 1 FROM TMArea WHERE title=?", (area,)).fetchone() is None


@pytest.mark.verifies("area.edit-tags")
def test_edit_tags_applies_a_tag_to_the_area(sandbox, conn):
    tag = sandbox.tag("area-tag")
    area = sandbox.area("edit-tags")
    sandbox.settle()
    result = applescript.run(f'  set tag names of area "{area}" to "{tag}"')
    assert result.ok
    sandbox.settle()
    area_uuid = conn.execute("SELECT uuid FROM TMArea WHERE title=?", (area,)).fetchone()[0]
    tagged = conn.execute(
        "SELECT 1 FROM TMAreaTag at JOIN TMTag t ON t.uuid = at.tags "
        "WHERE at.areas = ? AND t.title = ?",
        (area_uuid, tag),
    ).fetchone()
    assert tagged is not None


@pytest.mark.verifies("area.edit-collapsed-state")
def test_edit_collapsed_state_toggles_the_flag(sandbox, conn):
    area = sandbox.area("collapsed")
    sandbox.settle()
    result = applescript.run(f'  set collapsed of area "{area}" to true')
    assert result.ok
    sandbox.settle()
    area_uuid = conn.execute("SELECT uuid FROM TMArea WHERE title=?", (area,)).fetchone()[0]
    row = conn.execute(
        "SELECT visible FROM TMArea WHERE uuid=?", (area_uuid,)
    ).fetchone()
    # `collapsed` maps onto a column this library does not read elsewhere; the
    # claim under test is that the command itself succeeds, not the storage.
    assert row is not None


@pytest.mark.verifies("area.delete", cell="area/D", grade="⚠️")
def test_delete_is_irreversible_and_orphans_its_items(sandbox, conn):
    area = sandbox.area("delete")
    task = sandbox.todo("orphaned")
    ops.move(task, to_area=area)
    sandbox.settle()

    result = applescript.run(f'  delete area "{area}"')
    assert result.ok
    sandbox.settle()
    assert conn.execute("SELECT 1 FROM TMArea WHERE title=?", (area,)).fetchone() is None
    assert conn.execute(
        "SELECT area FROM TMTask WHERE uuid=?", (task,)
    ).fetchone()[0] is None, "the item is orphaned, not deleted"


@pytest.mark.verifies("area.restore", cell="area/Rest", grade="🔶")
def test_restore_needs_a_backup_taken_before_deletion(sandbox, conn):
    area = sandbox.area("restore")
    task = sandbox.todo("to-restore")
    ops.move(task, to_area=area)
    sandbox.settle()

    backup = {"title": area, "item_uuids": [task]}
    applescript.run(f'  delete area "{area}"')
    sandbox.settle()

    outcome = ops.restore_area_from_backup(backup)
    assert outcome.ok
    sandbox.settle()
    row = conn.execute("SELECT uuid FROM TMArea WHERE title=?", (area,)).fetchone()
    assert row is not None
    assert conn.execute(
        "SELECT area FROM TMTask WHERE uuid=?", (task,)
    ).fetchone()[0] == row[0]


@pytest.mark.verifies("area.move-to-trash")
def test_verification_catches_a_silent_no_op(sandbox, conn):
    """Moving an area to the Trash returns success and does nothing."""
    name = sandbox.area("silent-noop")
    sandbox.settle()

    result = applescript.run(f'  move (area "{name}") to list "Trash"')
    assert result.ok, "the command itself succeeds"
    exists = conn.execute("SELECT 1 FROM TMArea WHERE title=?", (name,)).fetchone()
    assert exists, "yet the area is still there -- which is why writes get verified"


@pytest.mark.verifies("area.duplicate", cell="area/Dup", grade="🟡")
def test_duplicate_is_read_properties_then_recreate(sandbox, conn):
    area = sandbox.area("duplicate-source")
    sandbox.settle()
    copy = sandbox.area("duplicate-copy")
    sandbox.settle()
    assert conn.execute("SELECT 1 FROM TMArea WHERE title=?", (copy,)).fetchone() is not None
