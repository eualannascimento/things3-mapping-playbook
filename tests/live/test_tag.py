"""Reproduce every tag recipe in the playbook against a real Things install."""
from __future__ import annotations

import pytest

from things3 import applescript, ops, read


pytestmark = pytest.mark.live


@pytest.mark.verifies("tag.read", cell="tag/R", grade="✅")
def test_read_returns_the_tag_name(sandbox):
    tag = sandbox.tag("read")
    sandbox.settle()
    result = applescript.run(f'  return name of every tag whose name is "{tag}"')
    assert result.ok
    assert tag in result.stdout


@pytest.mark.verifies("tag.create", cell="tag/C", grade="✅")
def test_create_makes_a_tag_reachable_by_name(sandbox, conn):
    tag = sandbox.tag("create")
    sandbox.settle()
    assert conn.execute("SELECT 1 FROM TMTag WHERE title=?", (tag,)).fetchone() is not None


@pytest.mark.verifies("tag.rename", cell="tag/U", grade="✅")
def test_rename_propagates_to_tagged_items(sandbox, conn):
    tag = sandbox.tag("rename-before")
    task = sandbox.todo("rename-tagged")
    sandbox.settle()
    applescript.run(f'  set tag names of to do id "{task}" to "{tag}"')
    sandbox.settle()

    assert ops.rename(ops.Kind.TAG, tag, "zzlive-rename-after", by_id=False).ok
    sandbox.settle()
    titles = read.task_tags(conn).get(task, set())
    assert "zzlive-rename-after" in titles
    assert tag not in titles


@pytest.mark.verifies("tag.edit-hierarchy", cell="tag/Move", grade="✅")
def test_edit_hierarchy_sets_the_parent_tag(sandbox, conn):
    parent = sandbox.tag("parent")
    child = sandbox.tag("child")
    sandbox.settle()
    result = applescript.run(f'  set parent tag of tag "{child}" to tag "{parent}"')
    assert result.ok
    sandbox.settle()
    parent_uuid = conn.execute("SELECT uuid FROM TMTag WHERE title=?", (parent,)).fetchone()[0]
    assert conn.execute(
        "SELECT parent FROM TMTag WHERE title=?", (child,)
    ).fetchone()[0] == parent_uuid


@pytest.mark.verifies("tag.edit-shortcut")
def test_edit_shortcut_sets_the_keyboard_shortcut(sandbox, conn):
    tag = sandbox.tag("shortcut")
    sandbox.settle()
    result = applescript.run(f'  set keyboard shortcut of tag "{tag}" to "z"')
    assert result.ok
    sandbox.settle()
    assert conn.execute(
        "SELECT shortcut FROM TMTag WHERE title=?", (tag,)
    ).fetchone()[0] == "z"


@pytest.mark.verifies("tag.apply-to-an-item")
def test_apply_to_an_item_replaces_the_whole_list(sandbox, conn):
    tag_a, tag_b = sandbox.tag("apply-a"), sandbox.tag("apply-b")
    task = sandbox.todo("apply-tags")
    sandbox.settle()
    applescript.run(f'  set tag names of to do id "{task}" to "{tag_a}"')
    sandbox.settle()
    applescript.run(f'  set tag names of to do id "{task}" to "{tag_a}, {tag_b}"')
    sandbox.settle()
    titles = read.task_tags(conn).get(task, set())
    assert titles == {tag_a, tag_b}


@pytest.mark.verifies("tag.delete", cell="tag/D", grade="⚠️")
def test_delete_is_irreversible_and_does_not_go_through_the_trash(sandbox, conn):
    tag = sandbox.tag("delete")
    sandbox.settle()
    result = applescript.run(f'  delete tag "{tag}"')
    assert result.ok
    sandbox.settle()
    assert conn.execute("SELECT 1 FROM TMTag WHERE title=?", (tag,)).fetchone() is None


@pytest.mark.verifies("tag.restore", cell="tag/Rest", grade="🔶")
def test_restore_needs_a_backup_taken_before_deletion(sandbox, conn):
    tag = sandbox.tag("restore")
    task = sandbox.todo("tagged-to-restore")
    sandbox.settle()
    applescript.run(f'  set tag names of to do id "{task}" to "{tag}"')
    sandbox.settle()

    applescript.run(f'  delete tag "{tag}"')
    sandbox.settle()

    ops.create(ops.Kind.TAG, tag)
    sandbox.settle()
    applescript.run(f'  set tag names of to do id "{task}" to "{tag}"')
    sandbox.settle()
    titles = read.task_tags(conn).get(task, set())
    assert tag in titles


@pytest.mark.verifies("tag.duplicate", cell="tag/Dup", grade="🟡")
def test_duplicate_is_read_properties_then_recreate(sandbox, conn):
    tag = sandbox.tag("duplicate-source")
    sandbox.settle()
    copy = sandbox.tag("duplicate-copy")
    sandbox.settle()
    assert conn.execute("SELECT 1 FROM TMTag WHERE title=?", (copy,)).fetchone() is not None
