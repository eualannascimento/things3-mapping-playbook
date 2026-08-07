"""URL scheme backend: the only path to headings and checklist items.

Two things that are not obvious, both verified live:

1. Opening with `open -g -j` keeps Things in the background. Without the flags,
   and with the app closed, it steals the user's focus.

2. `checklist-items` is documented only as a *create* attribute, but it works on
   `operation: update` and **replaces the whole list** -- the only way to edit
   the text of an existing checklist item. Meanwhile `append-checklist-items`
   and `prepend-checklist-items`, which *are* documented, do nothing at all.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.parse

BASE = "things:///json"

# -g: do not bring the app to the foreground. -j: launch it hidden if closed.
OPEN_COMMAND = ["open", "-g", "-j"]

MAX_CHECKLIST_ITEMS = 100


class MissingTokenError(RuntimeError):
    pass


def auth_token() -> str:
    """Read the Things auth token from the environment.

    Only ever from `os.environ` -- never from a command-line argument (visible in
    the process list and shell history) and never written to a file.
    """
    token = os.environ.get("THINGS_AUTH_TOKEN")
    if not token:
        raise MissingTokenError(
            "This operation uses 'operation: update', which Things requires an "
            "auth token for.\n"
            "Set THINGS_AUTH_TOKEN in your environment before running.\n"
            "Get it in: Things -> Settings -> General -> Enable Things URLs -> Manage."
        )
    return token


def build_url(payload: list[dict], *, token: str | None = None) -> str:
    compact = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    url = f"{BASE}?data=" + urllib.parse.quote(compact, safe="")
    if token:
        url += "&auth-token=" + urllib.parse.quote(token, safe="")
    return url


def send(payload: list[dict], *, needs_token: bool = False) -> str:
    """Send a payload to Things without bringing it to the foreground."""
    token = auth_token() if needs_token else None
    url = build_url(payload, token=token)
    subprocess.run(OPEN_COMMAND + [url], check=True)
    return url


def checklist_payload(items: list[dict]) -> list[dict]:
    """Build the `checklist-items` array.

    Each item needs `completed` sent explicitly: since the update replaces the
    whole list, anything not sent is lost -- including which items were checked.
    """
    return [
        {"type": "checklist-item",
         "attributes": {"title": i["title"], "completed": bool(i.get("completed"))}}
        for i in items
    ]


def replace_checklist(task_uuid: str, items: list[dict]) -> str:
    """Replace a task's entire checklist with `items`.

    This is the workaround for checklist items not accepting `update`: rebuild
    the list with the change applied and send it whole.
    """
    if len(items) > MAX_CHECKLIST_ITEMS:
        raise ValueError(
            f"Things caps checklists at {MAX_CHECKLIST_ITEMS} items; got {len(items)}. "
            "Refusing rather than silently truncating."
        )
    return send(
        [{"type": "to-do", "operation": "update", "id": task_uuid,
          "attributes": {"checklist-items": checklist_payload(items)}}],
        needs_token=True,
    )


def move_to_heading(task_uuid: str, project_uuid: str, heading_uuid: str) -> str:
    """Move a to-do under a heading -- not reachable from AppleScript."""
    return send(
        [{"type": "to-do", "operation": "update", "id": task_uuid,
          "attributes": {"list-id": project_uuid, "heading-id": heading_uuid}}],
        needs_token=True,
    )


def create_project_with_headings(title: str, heading_titles: list[str],
                                 area: str | None = None) -> str:
    """Create a project with headings.

    Headings can only be created together with their project: adding one to an
    existing project is impossible (five variations tested). To reshape an
    existing project's headings, create a new one and *move* the to-dos over --
    moving preserves uuid, checklist and recurrence; recreating would not.
    """
    attributes: dict = {
        "title": title,
        "items": [{"type": "heading", "attributes": {"title": t}} for t in heading_titles],
    }
    if area:
        attributes["area"] = area
    return send([{"type": "project", "attributes": attributes}])
