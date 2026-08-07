import plistlib
import sqlite3

import pytest

from things3 import applescript, guards, ops


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE TMTask (uuid TEXT PRIMARY KEY, title TEXT, type INT, "
              "trashed INT, status INT, area TEXT, rt1_recurrenceRule BLOB, "
              "rt1_repeatingTemplate TEXT)")
    c.execute("CREATE TABLE TMArea (uuid TEXT PRIMARY KEY, title TEXT)")
    c.execute("CREATE TABLE TMTag (uuid TEXT PRIMARY KEY, title TEXT)")
    c.execute("CREATE TABLE TMTaskTag (tasks TEXT, tags TEXT)")
    rule = plistlib.dumps({"fa": 1, "fu": 16, "of": [{"dy": 0}]})
    c.execute("INSERT INTO TMTask VALUES ('rep','Daily routine',0,0,0,NULL,?,NULL)", (rule,))
    c.execute("INSERT INTO TMTask VALUES ('plain','One-off',0,0,0,'a1',NULL,NULL)")
    c.execute("INSERT INTO TMArea VALUES ('a1','Health')")
    return c


@pytest.fixture
def fake_run(monkeypatch):
    """Capture the script instead of touching a real Things install."""
    calls = []

    def run(body, **kwargs):
        calls.append(body)
        return applescript.Result(0, "new-uuid", "")

    monkeypatch.setattr(ops.applescript, "run", run)
    return calls


# --- the delete asymmetry ---------------------------------------------------

def test_deleting_an_area_requires_explicit_opt_in(conn, fake_run):
    """Area deletion never reaches the Trash, so it cannot be a casual call."""
    with pytest.raises(ops.ConfirmationRequired, match="irreversible"):
        ops.delete(conn, ops.Kind.AREA, "Health")


def test_deleting_an_area_backs_up_its_items_first(conn, fake_run, tmp_path):
    outcome = ops.delete(conn, ops.Kind.AREA, "Health",
                         by_id=False, allow_irreversible=True, backup_dir=tmp_path)
    assert outcome.ok
    assert outcome.backup_path is not None
    assert "plain" in outcome.backup_path.read_text(encoding="utf-8")


def test_deleting_a_todo_needs_no_opt_in_and_says_it_is_reversible(conn, fake_run):
    outcome = ops.delete(conn, ops.Kind.TODO, "plain")
    assert outcome.ok
    assert "reversible" in outcome.detail
    assert outcome.backup_path is None


def test_deleting_a_repeating_task_is_refused(conn, fake_run):
    """Recurrence cannot be rebuilt by any API, so this has to be blocked."""
    with pytest.raises(guards.RecurrenceGuardError):
        ops.delete(conn, ops.Kind.TODO, "rep")


def test_deleting_a_heading_explains_the_only_route(conn, fake_run):
    with pytest.raises(ops.UnsupportedOperation, match="move the to-dos over"):
        ops.delete(conn, ops.Kind.HEADING, "uuid")


# --- restore ----------------------------------------------------------------

def test_restoring_an_area_is_refused_with_the_reason(fake_run):
    with pytest.raises(ops.UnsupportedOperation, match="never reaches the Trash"):
        ops.restore(ops.Kind.AREA, "Health")


def test_restoring_a_todo_moves_it_out_of_the_trash(fake_run):
    ops.restore(ops.Kind.TODO, "uuid")
    assert 'to list "Anytime"' in fake_run[0]


def test_area_can_be_rebuilt_from_its_backup(monkeypatch, fake_run):
    monkeypatch.setattr(ops.applescript, "run_batch", lambda statements: {})
    outcome = ops.restore_area_from_backup({"title": "Health", "item_uuids": ["t1", "t2"]})
    assert outcome.ok
    assert "2 item(s)" in outcome.detail


# --- move: the 301 trap -----------------------------------------------------

def test_moving_to_a_project_uses_set_not_move(fake_run):
    """`move ... to project` fails with 301 -- the dictionary types it as `list`."""
    ops.move("uuid", to_project="Work")
    assert "set project of" in fake_run[0]
    assert "move (" not in fake_run[0]


def test_moving_to_a_list_uses_move(fake_run):
    ops.move("uuid", to_list="Today")
    assert 'move (to do id "uuid") to list "Today"' in fake_run[0]


def test_move_requires_a_destination(fake_run):
    with pytest.raises(ValueError, match="to_list, to_project, to_area"):
        ops.move("uuid")


# --- headings ---------------------------------------------------------------

def test_heading_is_addressed_as_a_todo(fake_run):
    """No `heading` class exists; the object is only reachable via `to do id`."""
    ops.rename(ops.Kind.HEADING, "head-uuid", "New name")
    assert 'to do id "head-uuid"' in fake_run[0]


def test_heading_cannot_be_addressed_by_name(fake_run):
    with pytest.raises(ops.UnsupportedOperation, match="only be addressed by uuid"):
        ops.rename(ops.Kind.HEADING, "Some heading", "New", by_id=False)


def test_heading_cannot_be_created_standalone(fake_run):
    with pytest.raises(ops.UnsupportedOperation, match="together with its project"):
        ops.create(ops.Kind.HEADING, "My heading")


# --- bulk -------------------------------------------------------------------

def test_bulk_delete_refuses_irreversible_types(conn):
    with pytest.raises(ops.ConfirmationRequired, match="one at a time"):
        ops.delete_many(conn, ops.Kind.AREA, ["Health"])


def test_bulk_delete_checks_recurrence_before_touching_anything(conn, monkeypatch):
    called = []
    monkeypatch.setattr(ops.applescript, "run_batch", lambda s: called.append(s) or {})
    with pytest.raises(guards.RecurrenceGuardError):
        ops.delete_many(conn, ops.Kind.TODO, ["plain", "rep"])
    assert called == [], "nothing may be deleted if any item fails the guard"


def test_bulk_delete_sends_one_statement_per_uuid(conn, monkeypatch):
    captured = []
    monkeypatch.setattr(ops.applescript, "run_batch", lambda s: captured.extend(s) or {})
    ops.delete_many(conn, ops.Kind.TODO, ["plain"])
    assert captured[0][0] == "plain"


# --- misc -------------------------------------------------------------------

def test_status_rejects_unknown_values(fake_run):
    with pytest.raises(ValueError, match="Invalid status"):
        ops.set_status(ops.Kind.TODO, "uuid", "done")


def test_titles_with_quotes_are_escaped(fake_run):
    ops.create(ops.Kind.TODO, 'Say "hello"')
    assert '\\"hello\\"' in fake_run[0]
