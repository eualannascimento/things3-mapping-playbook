"""Read Things 3 data from its local SQLite database. Read-only, always.

Reading is the only path that sees everything: checklist items, headings and
recurrence are invisible to AppleScript, and the URL scheme cannot read at all.

The schema is not documented by Cultured Code and may change between versions,
so every query here fails loudly instead of returning partial data.
"""
from __future__ import annotations

import glob
import os
import plistlib
import sqlite3
import time
from pathlib import Path

DB_GLOB = os.path.expanduser(
    "~/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac/"
    "ThingsData-*/Things Database.thingsdatabase/main.sqlite"
)

# TMTask.type
TYPE_TODO, TYPE_PROJECT, TYPE_HEADING = 0, 1, 2
# TMTask.status / TMChecklistItem.status
STATUS_OPEN, STATUS_CANCELED, STATUS_COMPLETED = 0, 2, 3

# TMTask.rt1_recurrenceRule -> "fu" (frequency unit). Inferred by correlating
# real recurring tasks; not documented by Cultured Code. Good enough to display
# or to block a destructive operation, never to decide what to write.
_FREQ_UNIT = {16: "daily", 256: "weekly", 8: "monthly", 4: "yearly"}


def find_database(*, retries: int = 0, delay_seconds: float = 30.0) -> Path:
    """Locate the Things database.

    With retries > 0, waits and tries again -- useful right after boot, when the
    app's group container may not be mounted yet.
    """
    for attempt in range(retries + 1):
        found = glob.glob(DB_GLOB)
        if found:
            return Path(max(found, key=os.path.getmtime))
        if attempt < retries:
            time.sleep(delay_seconds)
    raise FileNotFoundError(
        f"Things database not found at: {DB_GLOB}\n"
        "Things 3 must have been opened at least once on this Mac."
    )


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open the database read-only. This library never writes to SQLite."""
    path = db_path or find_database()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def tasks(conn: sqlite3.Connection, *, only_open: bool = True) -> list[dict]:
    sql = (
        "SELECT uuid, title, notes, status, trashed, area, project, heading, "
        "       creationDate, userModificationDate, startDate, deadline, "
        "       rt1_repeatingTemplate AS repeating_template "
        "FROM TMTask WHERE type = ? AND trashed = 0"
    )
    if only_open:
        sql += f" AND status = {STATUS_OPEN}"
    return _rows(conn, sql, (TYPE_TODO,))


def projects(conn: sqlite3.Connection) -> list[dict]:
    return _rows(
        conn,
        "SELECT uuid, title, notes, status, area FROM TMTask "
        "WHERE type = ? AND trashed = 0",
        (TYPE_PROJECT,),
    )


def headings(conn: sqlite3.Connection) -> list[dict]:
    """Headings are TMTask rows with type=2 -- invisible to AppleScript as a class."""
    return _rows(
        conn,
        'SELECT uuid, title, project, "index" FROM TMTask WHERE type = ? AND trashed = 0',
        (TYPE_HEADING,),
    )


def areas(conn: sqlite3.Connection) -> list[dict]:
    return _rows(conn, "SELECT uuid, title FROM TMArea")


def tags(conn: sqlite3.Connection) -> list[dict]:
    return _rows(conn, "SELECT uuid, title, parent FROM TMTag")


def task_tags(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """Tag titles per task uuid."""
    result: dict[str, set[str]] = {}
    sql = ("SELECT tt.tasks AS task_uuid, tag.title AS tag_title "
           "FROM TMTaskTag tt JOIN TMTag tag ON tag.uuid = tt.tags")
    for row in _rows(conn, sql):
        result.setdefault(row["task_uuid"], set()).add(row["tag_title"])
    return result


def checklist_items(conn: sqlite3.Connection, task_uuid: str | None = None) -> list[dict]:
    """Checklist items, ordered as they appear in the UI.

    Invisible to AppleScript and to the app's experimental JSON property; SQLite
    is the only way to read them.
    """
    sql = ('SELECT uuid, task AS task_uuid, title, status, "index" '
           'FROM TMChecklistItem')
    params: tuple = ()
    if task_uuid is not None:
        sql += " WHERE task = ?"
        params = (task_uuid,)
    sql += ' ORDER BY task, "index"'
    return _rows(conn, sql, params)


def recurrence(conn: sqlite3.Connection, task_uuid: str) -> dict | None:
    """Decode a task's recurrence rule, or None if it does not repeat.

    The rule is stored as a binary plist. There is no write path for recurrence
    in any Things API -- reading it exists so a tool can *refuse* to run a
    destructive operation on a repeating task, which could not be recreated.
    """
    row = conn.execute(
        "SELECT rt1_recurrenceRule FROM TMTask WHERE uuid = ?", (task_uuid,)
    ).fetchone()
    if row is None or row[0] is None:
        return None
    rule = plistlib.loads(row[0])
    occurrences = rule.get("of") or []
    return {
        "every": rule.get("fa"),
        "unit": _FREQ_UNIT.get(rule.get("fu"), f"unknown({rule.get('fu')})"),
        # Weekday numbering starts at Monday = 1.
        "weekdays": [o["wd"] for o in occurrences if "wd" in o],
        "raw": rule,
    }


def is_repeating(conn: sqlite3.Connection, task_uuid: str) -> bool:
    """True if the task is a repeating template or an instance of one.

    Both cases must be protected: deleting or recreating either one loses the
    recurrence, and no API can put it back.
    """
    row = conn.execute(
        "SELECT rt1_recurrenceRule IS NOT NULL AS is_template, "
        "       rt1_repeatingTemplate AS template "
        "FROM TMTask WHERE uuid = ?",
        (task_uuid,),
    ).fetchone()
    if row is None:
        return False
    return bool(row["is_template"]) or row["template"] is not None
