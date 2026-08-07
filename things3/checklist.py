"""Edit checklist items of an existing to-do -- the operation everyone says is impossible.

It is true that a `checklist-item` object cannot be the target of an update. But
a **to-do** can, and one of the attributes it accepts on update is
`checklist-items`, which replaces the whole list. Rebuild the list with the change
applied, resend it complete, and the edit lands -- without touching the task's
uuid, recurrence or history.

Because a full replacement is destructive by nature, everything here is dry-run
by default, backs up first, and verifies afterwards.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import guards, read, urlscheme


class StaleplanError(RuntimeError):
    """The checklist changed between building the plan and applying it."""


def _fingerprint(items: list[dict]) -> list[tuple[str, int]]:
    """What must not have changed: the titles and their checked state, in order."""
    return [(i["title"], i["status"]) for i in items]


@dataclass
class ChecklistPlan:
    task_uuid: str
    task_title: str
    before: list[dict]
    after: list[dict]
    backup_path: Path | None = field(default=None)

    @property
    def changed(self) -> bool:
        return [(i["title"], i.get("completed")) for i in self.after] != [
            (i["title"], i["status"] == read.STATUS_COMPLETED) for i in self.before
        ]


def _as_editable(items: list[dict]) -> list[dict]:
    return [
        {"title": i["title"], "completed": i["status"] == read.STATUS_COMPLETED}
        for i in items
    ]


def plan(conn, task_uuid: str, *, rename: dict[str, str] | None = None,
         remove: list[str] | None = None, add: list[dict] | None = None) -> ChecklistPlan:
    """Build the resulting checklist without writing anything.

    `rename` maps current title -> new title, for corruption no rule can fix on
    its own (a missing accent is not mojibake; it needs the right word).
    `remove` lists titles to drop. `add` appends new items.
    """
    rename, remove, add = rename or {}, remove or [], add or []
    current = read.checklist_items(conn, task_uuid)
    task = conn.execute(
        "SELECT title FROM TMTask WHERE uuid = ?", (task_uuid,)
    ).fetchone()
    if task is None:
        raise ValueError(f"Task {task_uuid} not found")

    after = []
    for item in _as_editable(current):
        if item["title"] in remove:
            continue
        item["title"] = rename.get(item["title"], item["title"])
        after.append(item)
    after.extend({"title": a["title"], "completed": bool(a.get("completed"))} for a in add)

    return ChecklistPlan(task_uuid, task["title"], current, after)


def apply(conn, plan: ChecklistPlan, *, backup_dir: Path | None = None,
          settle_seconds: float = 2.0, force: bool = False) -> ChecklistPlan:
    """Apply a plan: backup, replace the list, then verify against SQLite.

    Because the write replaces the whole list, a plan built from stale state
    would silently discard whatever changed in between -- someone ticking an item
    in the app while the plan was open, for instance. So the current state is
    re-read immediately before writing and compared against what the plan was
    built on; a mismatch aborts instead of clobbering. `force=True` skips that
    check, for callers that genuinely want to overwrite.

    Note this does *not* refuse repeating tasks. Replacing a checklist edits the
    task in place -- uuid, recurrence and history all survive. The recurrence
    guard exists for operations that would recreate the task.
    """
    import time

    if not plan.changed:
        return plan

    if not force:
        current = read.checklist_items(conn, plan.task_uuid)
        if _fingerprint(current) != _fingerprint(plan.before):
            raise StaleplanError(
                f"The checklist of {plan.task_uuid!r} changed after this plan was built. "
                "Writing now would replace the whole list and discard that change. "
                "Rebuild the plan, or pass force=True to overwrite deliberately."
            )

    plan.backup_path = guards.backup(
        plan.task_uuid,
        {"task_uuid": plan.task_uuid, "task_title": plan.task_title,
         "original_items": plan.before},
        directory=backup_dir,
    )
    urlscheme.replace_checklist(plan.task_uuid, plan.after)
    time.sleep(settle_seconds)

    fresh = read.connect()
    try:
        guards.verify_checklist(fresh, plan.task_uuid, plan.after)
    finally:
        fresh.close()
    return plan


def move_item(conn, item_title: str, from_task: str, to_task: str,
              *, backup_dir: Path | None = None) -> tuple[ChecklistPlan, ChecklistPlan]:
    """Move a checklist item between to-dos.

    There is no move operation, and `append-checklist-items` does nothing despite
    being documented. What works is replacing the list on **both** sides: rebuild
    the source without the item and the destination with it.
    """
    source_items = read.checklist_items(conn, from_task)
    moving = next((i for i in source_items if i["title"] == item_title), None)
    if moving is None:
        raise ValueError(f"Item {item_title!r} not found in task {from_task}")

    source_plan = plan(conn, from_task, remove=[item_title])
    target_plan = plan(conn, to_task, add=[
        {"title": item_title, "completed": moving["status"] == read.STATUS_COMPLETED}
    ])
    return (apply(conn, source_plan, backup_dir=backup_dir),
            apply(conn, target_plan, backup_dir=backup_dir))
