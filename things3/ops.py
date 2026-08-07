"""Guarded operations for everyday work.

Without this module the guarantee layer is theoretical: `applescript.run()` is
there, so anyone deleting an area would call it directly and get no backup, no
confirmation and no recurrence guard -- exactly what this project exists to
prevent. Every operation here routes through `guards`.

The rule behind the API: **the object type decides the recipe**, not the caller.
`delete()` is one function because "delete this" is one intent, but it does very
different things depending on what it's deleting -- and the caller shouldn't have
to remember which.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from . import applescript, guards, read


class Kind(str, Enum):
    TODO = "to do"
    PROJECT = "project"
    AREA = "area"
    TAG = "tag"
    HEADING = "heading"


# `delete` behaves differently per type -- verified live. Treating it as one
# uniform command is the mistake this table exists to prevent.
REVERSIBLE_DELETE = {Kind.TODO, Kind.PROJECT}
IRREVERSIBLE_DELETE = {Kind.AREA, Kind.TAG}


class UnsupportedOperation(RuntimeError):
    """The platform offers no route for this, not even by composition."""


class ConfirmationRequired(RuntimeError):
    """An irreversible operation was attempted without explicit opt-in."""


@dataclass
class Outcome:
    ok: bool
    detail: str
    backup_path: Path | None = None


def _trash_statement(kind: Kind, spec: str) -> str:
    """Pick the statement that actually works for sending something away.

    `delete` and `move ... to list "Trash"` are documented as equivalent for
    to-dos and projects, and both land the item in the Trash. They are not
    equally reliable: `delete (to do id "...")` intermittently fails with -1728
    ("can't get to do id") on objects that are readable by the very same
    specifier a moment earlier. `move ... to list "Trash"` has never failed in
    testing, so it is what this library uses.

    Areas and tags have no Trash, so `delete` is the only route -- and it is
    permanent, which is why callers must opt in.
    """
    if kind in REVERSIBLE_DELETE:
        return f'  move ({spec}) to list "Trash"'
    return f"  delete ({spec})"


def _specifier(kind: Kind, identifier: str, *, by_id: bool) -> str:
    """Build an AppleScript specifier.

    A heading has no class of its own, but the object is reachable as
    `to do id "<uuid>"` -- the only way to address one.
    """
    if kind is Kind.HEADING:
        if not by_id:
            raise UnsupportedOperation(
                "A heading can only be addressed by uuid: it is not a class in the "
                "dictionary, so there is no `heading \"name\"` form."
            )
        return f'to do id "{applescript.escape(identifier)}"'
    if by_id:
        return f'{kind.value} id "{applescript.escape(identifier)}"'
    return f'{kind.value} "{applescript.escape(identifier)}"'


def create(kind: Kind, title: str, **properties) -> Outcome:
    """Create a to-do, project, area or tag.

    Headings are not creatable here: they only exist as part of a project's
    creation payload (see `urlscheme.create_project_with_headings`).
    """
    if kind is Kind.HEADING:
        raise UnsupportedOperation(
            "A heading can only be created together with its project. Use "
            "urlscheme.create_project_with_headings()."
        )
    pairs = [f'name:"{applescript.escape(title)}"']
    for key, value in properties.items():
        pairs.append(f'{key.replace("_", " ")}:"{applescript.escape(str(value))}"')
    result = applescript.run(
        f'  return id of (make new {kind.value} with properties {{{", ".join(pairs)}}})'
    )
    if not result.ok:
        return Outcome(False, result.stderr.strip())
    return Outcome(True, result.stdout.strip())


def rename(kind: Kind, identifier: str, new_title: str, *, by_id: bool = True) -> Outcome:
    """Rename any object, including a heading."""
    spec = _specifier(kind, identifier, by_id=by_id)
    result = applescript.run(
        f'  set name of {spec} to "{applescript.escape(new_title)}"'
    )
    return Outcome(result.ok, result.stderr.strip() or new_title)


def move(task_uuid: str, *, to_list: str | None = None, to_project: str | None = None,
         to_area: str | None = None) -> Outcome:
    """Move a to-do.

    `move ... to` is typed as `list` in the dictionary, so moving to a project
    fails with `301`. Projects and areas need `set project of` / `set area of` --
    the single most common trap in Things automation.
    """
    spec = f'to do id "{applescript.escape(task_uuid)}"'
    if to_list:
        body = f'  move ({spec}) to list "{applescript.escape(to_list)}"'
    elif to_project:
        body = f'  set project of {spec} to project "{applescript.escape(to_project)}"'
    elif to_area:
        body = f'  set area of {spec} to area "{applescript.escape(to_area)}"'
    else:
        raise ValueError("Pass one of: to_list, to_project, to_area")
    result = applescript.run(body)
    return Outcome(result.ok, result.stderr.strip() or "moved")


def set_status(kind: Kind, identifier: str, status: str, *, by_id: bool = True) -> Outcome:
    """Complete, cancel or reopen. `status` is one of open/completed/canceled."""
    if status not in {"open", "completed", "canceled"}:
        raise ValueError(f"Invalid status: {status!r}")
    spec = _specifier(kind, identifier, by_id=by_id)
    result = applescript.run(f"  set status of {spec} to {status}")
    return Outcome(result.ok, result.stderr.strip() or status)


def delete(conn, kind: Kind, identifier: str, *, by_id: bool = True,
           allow_irreversible: bool = False, backup_dir: Path | None = None) -> Outcome:
    """Delete an object, applying the guard its type deserves.

    - **To-do and project**: goes to the native Trash. Reversible, so it runs
      without ceremony. Recurring tasks are still refused: sending a repeating
      template to the Trash loses a recurrence no API can rebuild.
    - **Area and tag**: gone for good, never touching the Trash. Requires
      `allow_irreversible=True` and always writes a backup first -- without it,
      there is no record of which items belonged to the area, and restoring
      becomes impossible.
    - **Heading**: no route at all. Removing one means rebuilding the project.
    """
    if kind is Kind.HEADING:
        raise UnsupportedOperation(
            "A heading cannot be deleted: `delete` rejects it with -1728 and the "
            "Trash with 301. To remove one, create a new project with the desired "
            "headings and move the to-dos over."
        )

    backup_path = None

    if kind in IRREVERSIBLE_DELETE:
        if not allow_irreversible:
            raise ConfirmationRequired(
                f"Deleting a {kind.name.lower()} is irreversible: it does not go to the "
                "Trash, and its items are left orphaned with no record of where they "
                "belonged. Pass allow_irreversible=True to proceed."
            )
        backup_path = guards.backup(
            f"{kind.name.lower()}_{identifier}",
            _snapshot_container(conn, kind, identifier),
            directory=backup_dir,
        )

    if kind is Kind.TODO and by_id:
        guards.refuse_if_repeating(conn, identifier, "delete")

    spec = _specifier(kind, identifier, by_id=by_id)
    result = applescript.run(_trash_statement(kind, spec))
    if not result.ok:
        return Outcome(False, result.stderr.strip(), backup_path)

    reversible = kind in REVERSIBLE_DELETE
    detail = "moved to Trash (reversible)" if reversible else "deleted permanently"
    return Outcome(True, detail, backup_path)


def restore(kind: Kind, identifier: str, *, to_list: str = "Anytime") -> Outcome:
    """Bring a to-do or project back from the Trash.

    Areas and tags cannot be restored this way -- their delete never reached the
    Trash. Rebuilding them needs the backup `delete()` wrote.
    """
    if kind not in REVERSIBLE_DELETE:
        raise UnsupportedOperation(
            f"A {kind.name.lower()} never reaches the Trash when deleted, so there is "
            "nothing to restore. Rebuild it from the backup taken at deletion."
        )
    spec = _specifier(kind, identifier, by_id=True)
    result = applescript.run(f'  move ({spec}) to list "{applescript.escape(to_list)}"')
    return Outcome(result.ok, result.stderr.strip() or f"restored to {to_list}")


def restore_area_from_backup(backup: dict) -> Outcome:
    """Rebuild a deleted area and relink its items, from a `delete()` backup."""
    created = create(Kind.AREA, backup["title"])
    if not created.ok:
        return created
    statements = [
        (uuid, f'set area of to do id "{applescript.escape(uuid)}" '
               f'to area "{applescript.escape(backup["title"])}"')
        for uuid in backup["item_uuids"]
    ]
    errors = applescript.run_batch(statements)
    if errors:
        return Outcome(False, f"{len(errors)} item(s) could not be relinked: {errors}")
    return Outcome(True, f"area rebuilt with {len(statements)} item(s)")


def _snapshot_container(conn, kind: Kind, identifier: str) -> dict:
    """Record what a container held, so an irreversible delete stays recoverable."""
    if kind is Kind.AREA:
        rows = conn.execute(
            "SELECT t.uuid FROM TMTask t JOIN TMArea a ON t.area = a.uuid "
            "WHERE a.title = ? AND t.trashed = 0",
            (identifier,),
        ).fetchall()
    else:  # tag
        rows = conn.execute(
            "SELECT tt.tasks AS uuid FROM TMTaskTag tt JOIN TMTag g ON g.uuid = tt.tags "
            "WHERE g.title = ?",
            (identifier,),
        ).fetchall()
    return {"kind": kind.value, "title": identifier,
            "item_uuids": [r[0] for r in rows]}


def delete_many(conn, kind: Kind, uuids: list[str]) -> dict[str, str]:
    """Delete several objects in one pass, isolating failures.

    Deleting while iterating the live collection fails partway through, because
    the delete mutates the collection being walked. Taking a snapshot of ids
    first -- which this signature forces -- is what avoids it.
    """
    if kind in IRREVERSIBLE_DELETE:
        raise ConfirmationRequired(
            "Bulk deletion is only offered for reversible types (to-do, project). "
            "Delete areas and tags one at a time, so each gets its own backup."
        )
    for uuid in uuids:
        if kind is Kind.TODO:
            guards.refuse_if_repeating(conn, uuid, "delete")
    spec_kind = "to do" if kind is Kind.TODO else "project"
    return applescript.run_batch([
        (uuid, f'move ({spec_kind} id "{applescript.escape(uuid)}") to list "Trash"')
        for uuid in uuids
    ])
