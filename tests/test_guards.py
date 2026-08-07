import plistlib
import sqlite3

import pytest

from things3 import guards, read


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE TMTask (uuid TEXT PRIMARY KEY, title TEXT, type INT, "
              "trashed INT, status INT, rt1_recurrenceRule BLOB, rt1_repeatingTemplate TEXT)")
    c.execute('CREATE TABLE TMChecklistItem (uuid TEXT, task TEXT, title TEXT, '
              'status INT, "index" INT)')
    # weekly on Monday and Wednesday (weekday numbering starts at Monday = 1)
    rule = plistlib.dumps({"fa": 1, "fu": 256, "of": [{"wd": 1}, {"wd": 3}]})
    c.execute("INSERT INTO TMTask VALUES ('template','Weekly review',0,0,0,?,NULL)", (rule,))
    c.execute("INSERT INTO TMTask VALUES ('instance','Weekly review',0,0,0,NULL,'template')")
    c.execute("INSERT INTO TMTask VALUES ('plain','One-off task',0,0,0,NULL,NULL)")
    return c


def test_recurrence_is_decoded_from_binary_plist(conn):
    r = read.recurrence(conn, "template")
    assert r["unit"] == "weekly"
    assert r["every"] == 1
    assert r["weekdays"] == [1, 3]


def test_recurrence_is_none_for_plain_task(conn):
    assert read.recurrence(conn, "plain") is None


def test_is_repeating_covers_template_and_instance(conn):
    """Both must be protected: either one losing recurrence is unrecoverable."""
    assert read.is_repeating(conn, "template") is True
    assert read.is_repeating(conn, "instance") is True
    assert read.is_repeating(conn, "plain") is False


def test_guard_blocks_destructive_operation_on_repeating_task(conn):
    with pytest.raises(guards.RecurrenceGuardError, match="repeating series"):
        guards.refuse_if_repeating(conn, "template", "recreate")


def test_guard_allows_plain_task(conn):
    guards.refuse_if_repeating(conn, "plain", "recreate")


def test_backup_writes_readable_json(tmp_path):
    path = guards.backup("t1", {"task_uuid": "t1", "items": ["a"]}, directory=tmp_path)
    assert path.exists()
    assert '"task_uuid": "t1"' in path.read_text(encoding="utf-8")


def test_verify_checklist_raises_on_mismatch(conn):
    conn.execute("INSERT INTO TMChecklistItem VALUES ('c1','plain','Actual',0,0)")
    with pytest.raises(guards.VerificationError):
        guards.verify_checklist(conn, "plain", [{"title": "Expected"}])


def test_verify_checklist_passes_when_matching(conn):
    conn.execute("INSERT INTO TMChecklistItem VALUES ('c1','plain','Same',0,0)")
    guards.verify_checklist(conn, "plain", [{"title": "Same"}])


def test_verify_field_catches_silent_no_op(conn):
    """A success return code does not prove the write had any effect."""
    with pytest.raises(guards.VerificationError):
        guards.verify_field(conn, "plain", "title", "Renamed")
