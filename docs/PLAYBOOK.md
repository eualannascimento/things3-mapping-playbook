# Playbook — the exact command for every action

One recipe per cell of the capability matrix. **Everything here was executed live** against Things
3 (3.22.11, macOS 26.5) and verified by re-reading the result, rather than inferred from a
reference — because on this platform behaviour and documentation don't always line up (see
`append-checklist-items`).

## Notation

| | Meaning |
|---|---|
| `AS:` | AppleScript, via `osascript`. Does not bring the app to the foreground |
| `URL:` | URL scheme. **Always open with `open -g -j`**, or it steals focus when the app is closed |
| `URL+T:` | URL scheme with `operation: update` — **requires** `THINGS_AUTH_TOKEN` in the environment |
| `SQL:` | Read from the local SQLite database, always `mode=ro`. Never write |
| `<uuid>` | The object's id |

Every `AS:` line goes inside `tell application "Things3" ... end tell`.

---

## To-do

| Action | Recipe |
|---|---|
| **Read** (one) | `AS: return name of to do id "<uuid>"` — or any property |
| **Read** (bulk) | `SQL: SELECT uuid,title,notes,status,area,project,heading FROM TMTask WHERE type=0 AND trashed=0` |
| **Read** (a list) | `AS: return name of every to do of list "Today"` |
| **Count** | `AS: return count of to dos of list "Today"` — does not materialise the objects, so it's cheap |
| **Create** | `AS: make new to do with properties {name:"Title"}` |
| **Create** (natural language) | `AS: parse quicksilver input "Buy bread #errands"` — extracts `#tag`, **does not** extract dates |
| **Rename** | `AS: set name of to do id "<uuid>" to "New title"` |
| **Edit** notes | `AS: set notes of to do id "<uuid>" to "line1\nline2"` — multi-line, quotes and accents all survive |
| **Edit** tags | `AS: set tag names of to do id "<uuid>" to "tag1, tag2"` — tags must already exist |
| **Edit** deadline | `AS: set due date of to do id "<uuid>" to (current date) + 86400` |
| **Edit** schedule | `AS: schedule (to do id "<uuid>") for (current date) + 86400` — `activation date` is read-only |
| **Edit** "this evening" | `URL+T: {"attributes":{"when":"evening"}}` |
| **Edit** reminder time | `URL+T: {"attributes":{"when":"today@15:30"}}` |
| **Delete** | `AS: delete (to do id "<uuid>")` — goes to the **native Trash**, reversible |
| **Restore** | `AS: move (to do id "<uuid>") to list "Anytime"` |
| **Duplicate** 🟡 | `duplicate` fails with `-1717`. Read the properties and create a new item from them |
| **Move** to a list | `AS: move (to do id "<uuid>") to list "Today"` |
| **Move** to a project 🟡 | `AS: set project of to do id "<uuid>" to project "Name"` — do **not** use `move ... to project`, it fails with `301` |
| **Move** to an area 🟡 | `AS: set area of to do id "<uuid>" to area "Name"` |
| **Move** under a heading 🟡 | `URL+T: {"attributes":{"list-id":"<project-uuid>","heading-id":"<heading-uuid>"}}` |
| **Complete** | `AS: set status of to do id "<uuid>" to completed` |
| **Cancel** | `AS: set status of to do id "<uuid>" to canceled` |
| **Reopen** | `AS: set status of to do id "<uuid>" to open` |
| **Recurrence** (read) 🟡 | `SQL: SELECT rt1_recurrenceRule FROM TMTask WHERE uuid=?` → `plistlib.loads(blob)` |
| **Recurrence** (create/edit) ❌ | No route at all. Only through the app's UI |

## Project

| Action | Recipe |
|---|---|
| **Read** | `AS: return name of every project` · `SQL: ... FROM TMTask WHERE type=1` |
| **Read** its to-dos | `AS: return name of every to do of project "Name"` |
| **Create** | `AS: make new project with properties {name:"Name"}` |
| **Create** with headings 🟡 | `URL: [{"type":"project","attributes":{"title":"P","items":[{"type":"heading","attributes":{"title":"H"}}]}}]` — the **only** way to have headings |
| **Rename** | `AS: set name of project "Old" to "New"` |
| **Edit** notes | `AS: set notes of project "Name" to "..."` |
| **Delete** | `AS: delete (project id "<uuid>")` — native Trash, reversible |
| **Restore** | `AS: move (project id "<uuid>") to list "Anytime"` |
| **Duplicate** 🟡 | read properties + `make new project`; then **move** the to-dos over (prefer moving to recreating) |
| **Move** to an area | `AS: set area of project "Name" to area "Area"` |
| **Complete** | `AS: set status of project "Name" to completed` |
| **Add a heading after creation** 🔶 | see "Expensive workarounds" below |

## Area

| Action | Recipe |
|---|---|
| **Read** | `AS: return name of every area` · `SQL: SELECT uuid,title FROM TMArea` |
| **Create** | `AS: make new area with properties {name:"Name"}` |
| **Rename** | `AS: set name of area "Old" to "New"` |
| **Edit** tags | `AS: set tag names of area "Name" to "tag1"` |
| **Edit** collapsed state | `AS: set collapsed of area "Name" to true` |
| **Delete** ⚠️ | `AS: delete area "Name"` — **irreversible**, does not go through the Trash. Its items are orphaned (`area = NULL`), not deleted |
| **Restore** 🔶 | only from a prior backup — see "Expensive workarounds" |
| **Move to Trash** | **does not exist**: the command returns success and does nothing. A false positive — do not trust the return code |
| **Duplicate** 🟡 | read properties + `make new area` |

## Tag

| Action | Recipe |
|---|---|
| **Read** | `AS: return name of every tag` · `SQL: SELECT uuid,title,parent FROM TMTag` |
| **Create** | `AS: make new tag with properties {name:"Name"}` |
| **Rename** | `AS: set name of tag "Old" to "New"` — propagates to every tagged item |
| **Edit** hierarchy | `AS: set parent tag of tag "Child" to tag "Parent"` |
| **Edit** shortcut | `AS: set keyboard shortcut of tag "Name" to "z"` |
| **Apply** to an item | `AS: set tag names of to do id "<uuid>" to "tag1, tag2"` — replaces all of them; to add one, read the current list and rewrite it whole |
| **Delete** ⚠️ | `AS: delete tag "Name"` — **irreversible**, does not go through the Trash |
| **Restore** 🔶 | only from a prior backup — see "Expensive workarounds" |
| **Duplicate** 🟡 | read properties + `make new tag` |

## Heading

Not a class in the AppleScript dictionary — but the object **is addressable as `to do id`**.

| Action | Recipe |
|---|---|
| **Read** 🟡 | `SQL: SELECT uuid,title,project FROM TMTask WHERE type=2 AND trashed=0` |
| **Read** (one, by uuid) 🟡 | `AS: return name of to do id "<heading-uuid>"` |
| **Create** 🟡 | only alongside the project: `URL: {"type":"project","attributes":{"items":[{"type":"heading",...}]}}` |
| **Rename** 🟡 | `AS: set name of to do id "<heading-uuid>" to "New"` — the **only** route that works |
| **Edit** status | `AS: set status of to do id "<uuid>" to completed` — writes `status=3`, apparently archiving it |
| **Delete** 🔶 | no command works (`delete` → `-1728`, Trash → `301`). See "Expensive workarounds" |
| **Move** between projects 🔶 | `set project of` runs and has **no** effect. See "Expensive workarounds" |
| **Duplicate** 🔶 | `duplicate` → `-1717`. Rebuild via the project |
| **Create in an existing project** 🔶 | five variations tested, none work. See "Expensive workarounds" |

## Checklist item

Invisible to AppleScript **and** to the app's `_private_experimental_ json` property. SQLite is the
only way to read them.

| Action | Recipe |
|---|---|
| **Read** 🟡 | `SQL: SELECT title,status,"index" FROM TMChecklistItem WHERE task=? ORDER BY "index"` (`status`: 0 open, 3 completed) |
| **Create** with the to-do | `URL: {"type":"to-do","attributes":{"checklist-items":[{"type":"checklist-item","attributes":{"title":"X","completed":false}}]}}` |
| **Append** to an existing to-do 🟡 | `append-checklist-items` is a **no-op** — accepted, silently ineffective. Use the list replacement below |
| **Rename / Edit** an item 🟡 | read the whole list, change the item, and **replace the entire list**: `URL+T: {"attributes":{"checklist-items":[...full corrected list...]}}`. Resend `completed` for every item, or whatever was checked is lost |
| **Delete** an item 🟡 | same replacement, omitting the item |
| **Move** between to-dos 🟡 | replacement on **both sides**: rebuild the source without the item and the destination with it |
| **Complete** an item 🟡 | same replacement, with `"completed": true` on that item |
| **Limit** | 100 items per to-do. Above that, refuse the operation rather than truncating silently |

## Application

| Action | Recipe |
|---|---|
| **Built-in lists** | `AS: return name of every list` → Inbox, Today, **Tomorrow**, Anytime, Upcoming, Someday, **Later Projects**, Logbook, Trash (nine, not seven — `Tomorrow` and `Later Projects` are undocumented) |
| **Current list** | `AS: return current list name` |
| **UI selection** | `AS: return name of every selected to do` |
| **Quick entry panel** | `AS: show quick entry panel with autofill` |
| **Archive completed** | `AS: log completed now` |
| **Empty the Trash** | `AS: empty trash` — **irreversible and global**. Never call this from automation |

---

## Expensive workarounds (🔶)

### Add, remove or move a heading in an existing project

None of those three has a command. All three are solved the same way, because **the task is the
expensive object and the project is just a shell**:

1. Create a **new project** with the heading structure you want (one `URL:` call).
2. **Move** each to-do into it: `AS: set project of ...`, and `URL+T:` with `heading-id` for the
   heading.
3. Delete the old project: `AS: delete (project id "<uuid>")` — goes to the Trash, reversible.

**Why move instead of recreate**: moving preserves the object — uuid, checklist items one by one
(including which were checked), recurrence and history. Recreating would destroy the recurrence,
which has no write API.

**Cost**: the project loses its original uuid (breaking deep links to the project; the tasks' own
links stay valid).

### Restore a deleted area or tag

`delete` on an area or tag **does not go through the Trash** — it's gone. Restoring requires a
prior backup:

1. **Before deleting**, record the name and the uuids of the items that belonged to it.
2. To restore: `AS: make new area with properties {name:"..."}` and, for each uuid in the backup,
   `AS: set area of to do id "<uuid>" to area "..."`.

**Without the backup there is no restore**: the items are left with `area = NULL` and nothing
records which one they belonged to. That's why deleting an area or tag demands a mandatory backup
and explicit confirmation.

---

## Traps this playbook avoids

| Trap | What happens if you hit it |
|---|---|
| `move ... to project` (instead of `set project of`) | fails with `Cannot move to-do (301)` |
| `open` without `-g -j` | steals the user's focus when the app is closed |
| `append-checklist-items` | a no-op: accepted, silently ineffective |
| Replacing a checklist without resending `completed` | everything that was checked is lost |
| Trusting the return code | "move an area to the Trash" returns success and does nothing |
| `repeat with t in to dos ... delete t` | fails halfway: deleting mutates the collection. Snapshot the ids first |
| Treating `delete` as one command | reversible on to-dos and projects, permanent on areas and tags |
| `empty trash` | wipes the user's entire Trash, irreversibly |
| `sdef` to inspect the API | needs full Xcode; without it, returns empty and becomes a false negative |
