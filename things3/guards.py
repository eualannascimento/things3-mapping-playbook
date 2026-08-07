"""Guarantees around writes. This is the part other Things wrappers don't have.

Be honest about what is and isn't possible: **there are no transactions**. Things
exposes nothing of the sort, and any project promising "atomic operations" on top
of it is overselling. What can be guaranteed, and is more useful in practice:

  - dry-run by default on anything destructive;
  - a backup written before the write, with its path reported;
  - verification after the write, by re-reading and comparing;
  - a recurrence guard, because a repeating task cannot be recreated;
  - retries only for transient errors (see `applescript.TRANSIENT_ERRORS`).

The verification step is not paranoia. A success return code does not prove the
operation had any effect: "move an area to the trash" returns success and does
nothing at all.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import read

DEFAULT_BACKUP_DIR = Path.home() / ".things3-playbook" / "backups"


class RecurrenceGuardError(RuntimeError):
    """Raised when a destructive operation targets a repeating task."""


class VerificationError(RuntimeError):
    """Raised when the state after a write does not match what was intended."""


def backup(name: str, data: dict, *, directory: Path | None = None) -> Path:
    """Write a JSON snapshot before a destructive operation."""
    target = directory or DEFAULT_BACKUP_DIR
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = target / f"{stamp}_{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def refuse_if_repeating(conn, task_uuid: str, operation: str) -> None:
    """Block a destructive operation on a repeating task.

    Recurrence has no write path in any Things API. A task that loses it cannot
    get it back -- so operations that would recreate the task are refused.
    """
    if read.is_repeating(conn, task_uuid):
        raise RecurrenceGuardError(
            f"'{operation}' refused: task {task_uuid} is part of a repeating series. "
            "Recurrence cannot be recreated by any Things API, so it would be lost "
            "for good. Move the task instead of recreating it, or do this in the app."
        )


def verify_checklist(conn, task_uuid: str, expected: list[dict]) -> None:
    """Confirm a checklist replacement landed exactly as intended."""
    actual = [i["title"] for i in read.checklist_items(conn, task_uuid)]
    wanted = [i["title"] for i in expected]
    if actual != wanted:
        raise VerificationError(
            f"Checklist of {task_uuid} does not match after the write.\n"
            f"  expected: {wanted}\n"
            f"  actual:   {actual}"
        )


def verify_field(conn, task_uuid: str, field: str, expected) -> None:
    """Confirm a single field landed. Guards against silent no-ops."""
    row = conn.execute(
        f"SELECT {field} FROM TMTask WHERE uuid = ?", (task_uuid,)
    ).fetchone()
    if row is None:
        raise VerificationError(f"Task {task_uuid} not found after the write.")
    if row[0] != expected:
        raise VerificationError(
            f"Field '{field}' of {task_uuid} is {row[0]!r}, expected {expected!r}."
        )
