# Architecture

Decision record. Written before the code, so the reasoning is auditable.

## 1. The problem

Automating Things 3 is frustrating enough that people migrate away over it. The usual complaint is
"there's no modern API" — and that's true: only AppleScript (Mac-only), the URL scheme, and an
undocumented local SQLite database.

But the diagnosis is incomplete. The public tools that exist today are all **thin wrappers**: they
expose what the platform gives and stop there. None of them address what actually hurts once an AI
agent writes into your task list:

- there's no way to tell whether a write **actually took effect**;
- there's no way to **undo** when it didn't;
- destructive operations don't know a task is **repeating** and cannot be recreated;
- a transient Apple Event failure is indistinguishable from a real one.

**This is not another wrapper.** The core is the guarantee layer that's missing.

### Non-goals

- No Things Cloud sync — local instance only.
- Not a replacement for the UI: what only exists there (recurrence, mainly) stays there.
- No iOS/iPadOS — AppleScript is Mac-only.

## 2. What the platform allows

Everything below was verified on a Mac, against the installed app — not copied from documentation.

| | C | R | U | D | Dup | Move | Done | Rest |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **To-do** | ✅ | ✅ | ✅ | ✅ | 🟡 | 🟡 | ✅ | ✅ |
| **Project** | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ |
| **Area** | ✅ | ✅ | ✅ | ⚠️ | 🟡 | ➖ | ➖ | 🔶 |
| **Tag** | ✅ | ✅ | ✅ | ⚠️ | 🟡 | ✅ | ➖ | 🔶 |
| **Heading** | 🟡 | 🟡 | 🟡 | 🔶 | 🔶 | 🔶 | ✅ | ➖ |
| **Checklist item** | ✅ | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | ✅ | ➖ |
| **Recurrence** | ❌ | 🟡 | ❌ | ❌ | ➖ | ➖ | ➖ | ➖ |

**Columns** — C create · R read · U update (rename and edit alike) · D delete · Dup duplicate ·
Move move · Done complete or cancel · Rest restore from the Trash

**Cells** — ✅ works directly · 🟡 cheap validated workaround · 🔶 expensive workaround (rebuild the
parent, or restore from a backup) · ⚠️ works but **irreversible** · ❌ impossible by any route,
including composition · ➖ not applicable

> **Criterion**: `❌` only when there is no path **even by composing operations**. If a sequence of
> supported steps reaches the result, it's 🟡 or 🔶 — never ❌. Every workaround here was executed
> live, not deduced.

The exact command for each cell is in [PLAYBOOK.md](PLAYBOOK.md); the full API inventory is in
[API-MAP.md](API-MAP.md).

### Findings that were expensive to reach

1. **A `checklist-item` doesn't accept `update`, but a `to-do` accepts `checklist-items`** — and
   that attribute *replaces the whole list*. Since the type accepts `title` + `completed`, the
   corrected list can be rebuilt without losing what was checked, the uuid, recurrence or history.
   It is the only way to edit the text of an existing subtask.

2. **`append-checklist-items` and `prepend-checklist-items` are no-ops.** The request is accepted,
   nothing changes, and no error is reported — the worst failure mode, since code using them looks
   like it works.

3. **`open -g -j` avoids bringing the app forward.** With Things closed, plain `open` steals focus;
   with both flags the operation happens the same and focus stays put.

4. **Recurrence is readable** in `TMTask.rt1_recurrenceRule` (binary plist). It is writable through
   no route — but *reading* it enables this project's most important safety guard.

5. **`move ... to` is typed as `list`.** That's why moving a to-do to a *project* fails with
   `Cannot move to-do (301)`. Use `set project of` / `set area of`.

6. **`sdef` requires full Xcode.** With only Command Line Tools it fails to stderr and returns an
   **empty** stdout — any `sdef ... | grep X` becomes a silent false negative.

7. **A heading is addressable as `to do id "<uuid>"`** despite not existing as a class. That is —
   and only that is — how you rename one.

8. **Moving preserves everything; recreating destroys.** Moving a to-do between projects keeps its
   uuid, checklist item by item (including what was checked), recurrence and history. Which is why
   the workaround for "add a heading to an existing project" is to create the new project and
   **move** the to-dos, never to recreate them.

### Ruled out: Apple Shortcuts

The Things Shortcuts actions (3.17+) offer checklist editing, `Find Items` and delete with a trash
option. They're **out of scope**: the only exclusive capability is editing checklists without a
credential, at the cost of requiring manual import of shortcuts (more friction than the credential
it avoids), raising the minimum version, and adding a third backend to maintain.

## 3. Design

Four layers. The rule that doesn't bend: **an upper layer never talks to Things directly.**

```
        skill / MCP            ← AI agents
             │
            cli                ← humans
             │
      ┌──────────────┐
      │  guarantees  │         ← where the value is
      └──────────────┘
        │          │
      read       write
    (sqlite)  (applescript · url scheme)
```

### 3.1 Reading — SQLite, read-only, always

The only path that sees everything (checklist items, headings, recurrence); fast, and it doesn't
disturb the app. Connections are always `mode=ro`; the database is **never** written to — the
schema isn't documented by Cultured Code and may change between versions.

### 3.2 Writing — the backend is chosen per operation, not by preference

| Operation | Backend | Why |
|---|---|---|
| To-do/project/area/tag fields | AppleScript | no credential, no focus stealing, granular |
| Create checklist items/headings | URL scheme (`open -g -j`) | AppleScript has no such class |
| Edit an existing checklist item | URL scheme + credential | it's an `operation: update` |

### 3.3 Guarantees — the core

On **atomicity**, be blunt: **real transactions are impossible.** Things exposes nothing of the
sort; any project promising "atomic operations" is overselling. What can genuinely be guaranteed,
and is more useful in practice:

| Guarantee | How |
|---|---|
| **Dry-run** | Every destructive operation computes and shows the plan without writing. That's the default; writing must be asked for |
| **Backup first** | Prior state written to JSON, path reported, before any destructive write |
| **Verify after** | Re-read from SQLite and compare against intent. A mismatch is reported as failure, never swallowed |
| **Recurrence guard** | Destructive operations on repeating tasks are **blocked** — they cannot be recreated by any API |
| **Classified retries** | Transient Apple Event errors (`-609`, `-600`, `-1712`) retried with backoff; permanent errors fail immediately |
| **Batch isolation** | Each item runs in its own `try`: one failure doesn't take down the rest, and the report is per item |
| **Limits respected** | Above 100 checklist items the replacement is refused rather than silently truncated |

What is **not** guaranteed, and must be stated plainly: automatic rollback (the backup is manual by
design — reverting blindly can make things worse), atomicity across multiple items, and anything
depending on recurrence being writable.

### 3.4 Policy on destructive operations

The policy has to reflect the **asymmetry of `delete`** found in testing:

| Object | What `delete` does | Policy |
|---|---|---|
| To-do, project | native Trash, **reversible** | allowed; it's the expected "delete" behaviour |
| Area, tag | **gone for good**, no Trash | behind a flag that's off by default + confirmation + backup |
| Heading | fails | not offered; documented |
| `empty trash` | wipes the Trash, **irreversible and global** | never called by automation |

**Only native Things resources.** No inventing structure (a "Trash" project, a control tag, a
system area) to work around something: the user's database is theirs, and invented structure
pollutes their UI and means nothing to the app.

## 4. Repository layout

```
things3-mapping-playbook/
├── things3/
│   ├── read.py        # read-only sqlite; recurrence decoding
│   ├── applescript.py # batching, retries, error classification
│   ├── urlscheme.py   # background open, checklist replacement
│   ├── guards.py      # backup, verification, recurrence guard
│   └── checklist.py   # the checklist editing operation
├── docs/
│   ├── ARCHITECTURE.md  # this document
│   ├── API-MAP.md       # verified API inventory + traps
│   └── PLAYBOOK.md      # exact command per type × action
└── tests/
```

## 5. Known risks

| Risk | Mitigation |
|---|---|
| The SQLite schema changes in a Things release | Tolerant reads + a suite that runs against a real database; fail explicitly instead of returning partial data |
| Checklist replacement loses data if interrupted | Mandatory backup before; verification after; refuse above 100 items |
| `rt1_recurrenceRule` semantics are inferred, not documented | Used only to *block* an operation (a false positive is safe; it never decides what to write) |
| Credential leaking into logs or shell history | Read only from an environment variable, never a command-line argument, never written to a file |
| A transient error masking a real one | Retries only for known codes, with a cap; everything else fails immediately |
