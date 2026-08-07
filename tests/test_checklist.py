import sqlite3

import pytest

from things3 import checklist, read


@pytest.fixture
def conn():
    """In-memory stand-in for the Things schema, with the columns we read."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE TMTask (uuid TEXT PRIMARY KEY, title TEXT, type INT, "
              "trashed INT, status INT, rt1_recurrenceRule BLOB, rt1_repeatingTemplate TEXT)")
    c.execute('CREATE TABLE TMChecklistItem (uuid TEXT, task TEXT, title TEXT, '
              'status INT, "index" INT)')
    c.execute("INSERT INTO TMTask VALUES ('t1','Morning routine',0,0,0,NULL,NULL)")
    c.execute("INSERT INTO TMTask VALUES ('t2','Other task',0,0,0,NULL,NULL)")
    items = [("c1", "t1", "Make the bed", 0, -3),
             ("c2", "t1", "Drink water", 3, -2),
             ("c3", "t1", "Stretch", 0, -1)]
    c.executemany("INSERT INTO TMChecklistItem VALUES (?,?,?,?,?)", items)
    return c


def test_plan_renames_item_and_keeps_the_rest(conn):
    p = checklist.plan(conn, "t1", rename={"Stretch": "Stretch for 5 min"})
    assert [i["title"] for i in p.after] == ["Make the bed", "Drink water", "Stretch for 5 min"]
    assert p.changed


def test_plan_preserves_completed_state(conn):
    """A full replacement drops anything not resent -- including what was checked."""
    p = checklist.plan(conn, "t1", rename={"Make the bed": "Make bed"})
    completed = {i["title"]: i["completed"] for i in p.after}
    assert completed["Drink water"] is True
    assert completed["Make bed"] is False


def test_plan_removes_item(conn):
    p = checklist.plan(conn, "t1", remove=["Drink water"])
    assert [i["title"] for i in p.after] == ["Make the bed", "Stretch"]


def test_plan_adds_item_at_the_end(conn):
    p = checklist.plan(conn, "t1", add=[{"title": "New item"}])
    assert p.after[-1] == {"title": "New item", "completed": False}


def test_plan_reports_no_change_when_nothing_matches(conn):
    p = checklist.plan(conn, "t1", rename={"Does not exist": "Whatever"})
    assert not p.changed


def test_plan_preserves_order(conn):
    """Order comes from the `index` column, which is negative and ascending."""
    p = checklist.plan(conn, "t1")
    assert [i["title"] for i in p.after] == ["Make the bed", "Drink water", "Stretch"]


def test_plan_raises_for_unknown_task(conn):
    with pytest.raises(ValueError):
        checklist.plan(conn, "does-not-exist")


def test_move_item_raises_when_item_missing(conn):
    with pytest.raises(ValueError, match="not found"):
        checklist.move_item(conn, "Nonexistent", "t1", "t2")


def test_read_checklist_orders_by_index(conn):
    items = read.checklist_items(conn, "t1")
    assert [i["title"] for i in items] == ["Make the bed", "Drink water", "Stretch"]
    assert items[1]["status"] == read.STATUS_COMPLETED
