# AppleScript API map

Exhaustive inventory, extracted from the real dictionary of the installed app and verified with
live tests. Source of truth: `/Applications/Things3.app/Contents/Resources/Things.sdef`.

> **Careful with `sdef`**: the `sdef /Applications/Things3.app` command **requires full Xcode**.
> With only the Command Line Tools installed it fails to stderr and returns an **empty** stdout —
> so `sdef … | grep X` looks like "X not found" when in fact nothing was read at all. Earlier
> versions of this research fell into exactly that trap. Always read the bundle's `.sdef` directly.

## Classes and properties

Access: `rw` read and write, `r` read-only.

### `to do`

| Property | Type | Access |
|---|---|---|
| `id` | text | r |
| `name` | text | rw |
| `notes` | text | rw |
| `status` | status (`open` \| `completed` \| `canceled`) | rw |
| `tag names` | text (comma-separated) | rw |
| `creation date` | date | rw |
| `modification date` | date | rw |
| `due date` | date | rw |
| `activation date` | date | **r** |
| `completion date` | date | rw |
| `cancellation date` | date | rw |
| `project` | project | rw |
| `area` | area | rw |
| `contact` | contact | rw |
| `_private_experimental_ json` | text | r |

Element: `tag`.

`activation date` is read-only — to schedule, use the `schedule` command (or the URL scheme).

### `project`

Inherits from `to do` (same properties). Additional element: `to do`.

### `area`

| Property | Type | Access |
|---|---|---|
| `tag names` | text | rw |
| `collapsed` | boolean | rw |

Elements: `to do`, `tag`. **`name` is not listed among the class properties** — but it works in
practice, coming from AppleScript's default container behaviour.

### `tag`

| Property | Type | Access |
|---|---|---|
| `id` | text | r |
| `name` | text | rw |
| `keyboard shortcut` | text | rw |
| `parent tag` | tag | rw |

Elements: `tag`, `to do`. `parent tag` is what enables the nested tag hierarchy.

### `list`

| Property | Type | Access |
|---|---|---|
| `id` | text | r |
| `name` | text | rw |

Element: `to do`. The nine built-in lists: `Inbox`, `Today`, `Tomorrow`, `Anytime`, `Upcoming`,
`Someday`, `Later Projects`, `Logbook`, `Trash`. (`Tomorrow` and `Later Projects` appear in no
documentation.)

### `contact`

No properties of its own; element `to do`. Created by `add contact named`.

### `application`

| Property | Type | Access |
|---|---|---|
| `name`, `frontmost`, `version` | — | r |
| `current list url` | text | r |
| `current list name` | text | r |
| `_private_experimental_ current list json` | text | r |

Elements: `window`, `list`, `to do`, `project`, `area`, `contact`, `tag`, `selected to do`.

## Commands

### Standard Suite

| Command | Signature | Note |
|---|---|---|
| `count` | `count <specifier> [each <type>]` → integer | Counts without materialising the objects — far cheaper than iterating |
| `exists` | `exists <any>` → boolean | Existence check |
| `make` | `make new <type> [at <location>] [with properties <record>]` → specifier | |
| `delete` | `delete <specifier>` | **Asymmetric** — see below |
| `duplicate` | `duplicate <specifier> [to <location>] [with properties <record>]` → specifier | Fails with `-1717` for to-dos |
| `close`, `print`, `quit` | — | Window/app, unused here |

### Things Suite

| Command | Signature | Note |
|---|---|---|
| `show` | `show <item>` | Navigates to the item in the UI |
| `edit` | `edit <to do>` | Opens the item in edit mode |
| `move` | `move <to do> to <list>` | **The `to:` parameter is typed as `list`** — which is why moving to a *project* fails with `Cannot move to-do (301)`. For projects/areas use `set project of` / `set area of` |
| `schedule` | `schedule <to do> for <date>` | The only write path for the activation date |
| `log completed now` | — | Moves completed items to the Logbook immediately |
| `empty trash` | — | **Irreversible and global** — wipes the entire Trash |
| `show quick entry panel` | `[with autofill <boolean>] [with properties <record>]` | `with autofill` is the autofill-from-frontmost-app feature |
| `parse quicksilver input` | `parse quicksilver input <text>` → to do | Things' own quick-entry parser (see limits below) |
| `add contact named` | `add contact named <text>` → contact | |
| `get localized string` | `get localized string <text> from <text>` → text | |
| `filter by previous/next top tag` | — | UI navigation |
| `_private_experimental_ reorder to dos in` | `<list> with ids <text>` | Reordering; private API, may vanish without notice |

## `delete` is asymmetric

Verified live. Treating it as a single command would be a serious mistake:

| Object | What `delete` does |
|---|---|
| To-do, project | goes to the **native Trash** (`trashed=1`), **reversible** via `move ... to list "Anytime"` |
| Area, tag | **gone for good**, never touches the Trash. Items are orphaned, not deleted |
| Heading | fails with `-1728` |

## What the AppleScript API does not cover

Verified against the real dictionary (zero occurrences) and confirmed by testing:

| Feature | Status | Alternative |
|---|---|---|
| **Checklist items** | Absent from the dictionary. The to-do's `_private_experimental_ json` **also** omits them (tested) | Read: SQLite (`TMChecklistItem`). Write: URL scheme `things:///json` |
| **Headings** | Absent as a class — but the object **is addressable as `to do id "<uuid>"`**, which is the only way to rename one | Create: URL scheme. Read: SQLite (`TMTask` with `type=2`) |
| **Recurrence** | Absent from the dictionary **and** from the URL scheme | Read only: `TMTask.rt1_recurrenceRule`, a binary plist |
| **Efficient bulk reads** | Iterating `to dos` is slow | SQLite, read-only |

## Headings: what works and what doesn't

| Operation | Works? | How |
|---|---|---|
| Read | yes | SQLite (`type=2`), or AppleScript via `to do id` |
| Rename | **yes** | `set name of to do id "<uuid>"` — this route only; the URL scheme fails |
| Create alongside the project | yes | `items` array of a `project` in `operation: create` |
| Create in an **existing** project | **no** | five variations tested, all failed |
| Move a to-do under a heading | yes | `to-do` + `update` + `heading-id` (needs auth token) |
| Move a heading between projects | **no** | `set project of` runs without error and without effect |
| Archive/hide a heading | apparently | `set status ... to completed` writes `status=3` |
| Delete a heading | **no** | `delete` rejects with `-1728`; Trash fails with `301`; `duplicate` fails with `-1717` |

Failed variations for creating a heading in an existing project: `heading` with `list-id`;
`heading` with `list` (title); a to-do created with `heading` pointing at a non-existent name (the
to-do is created, the heading is not); `project` + `update` with `items`; `duplicate` of an
existing heading into another project.

**Workaround** — no need to recreate everything. The task is the expensive object; the project is a
shell. Create a new project with the desired headings, **move** the to-dos into it, then delete the
old project. Moving preserves the object entirely: uuid, checklist item by item (including what was
checked), recurrence and history. Recreating the tasks would destroy the recurrence, which has no
write API.

## URL scheme without bringing the app forward

Tested with Things **closed** (the decisive case — with it already running, neither steals focus):

| Command | App closed | Item created? |
|---|---|---|
| `open things:///...` | **steals focus** | yes |
| `open -g -j things:///...` | **does not steal focus** | yes |

`-g` (`--background`) keeps the app from coming forward; `-j` (`--hide`) launches it hidden if it
isn't running.

## Recurrence: readable in SQLite, never writable

`TMTask.rt1_recurrenceRule` is a **binary plist** (`plistlib.loads` decodes it directly). There is
still no write path — but being able to **read** it lets a tool detect "this task repeats" and
refuse to run a destructive operation on it.

Observed fields:

| Field | Inferred meaning | Examples |
|---|---|---|
| `fa` | frequency (every N) | `1` |
| `fu` | unit | `16` = daily, `256` = weekly |
| `of` | occurrences | `[{"dy":0}]` daily; `[{"wd":1},{"wd":3}]` weekly on days 1 and 3 |
| `tp`, `rrv`, `rc` | type/version/counter | `0`, `4`, `0` |
| `sr`, `ia`, `ed` | dates (Core Data epoch) | start, activation, end |

`wd` is the weekday, **starting at Monday = 1**.

> The semantics of `fu`/`wd` are **inferred** by correlating real usage, not documented by Cultured
> Code. Treat as a heuristic: fine for displaying or for blocking an operation, never for deciding
> what to write.

## Live test results

| Test | Result |
|---|---|
| Writing accented titles/notes via AppleScript | Perfectly preserved (identical round-trip) |
| Multi-line notes with quotes, accents and indentation | Perfectly preserved |
| Creating accented checklist items via URL scheme | Perfectly preserved |
| `parse quicksilver input` extracting `#tag` | **Yes** — the tag is applied |
| `parse quicksilver input` extracting a date | **No** — lands in the Inbox with no date, in both English and Portuguese |
| `count of to dos of list "Today"` | Works, without materialising objects |
| `activation date` | Read-only (`missing value` when unscheduled) |

## Known transient errors

They happen when the app is busy or launching; they deserve a retry with backoff, not a failure:

| Code | Meaning |
|---|---|
| `-609` | Connection is invalid |
| `-600` | Application isn't running |
| `-1712` | Apple Event timed out |

Permanent errors (do not retry): `-1728` (object does not exist), syntax errors.

## Another trap: deleting while iterating

`repeat with t in to dos ... delete t` fails partway through with `Can't get item N of every to do`,
because deleting mutates the collection being iterated. Snapshot the ids first, then delete one by
one.
