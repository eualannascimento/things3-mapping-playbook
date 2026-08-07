# things3-mapping-playbook

A verified map of what Things 3 automation can and cannot do — and the code to do it safely.

Everything here was executed against a real Things install (3.22.11, macOS 26.5) and verified by
re-reading the result. Nothing is copied from documentation. That matters, because **the official
documentation is wrong in at least one place** and the community tools inherit the mistake.

## Why this exists

People migrate away from Things because "it has no modern API". That is true — there is only
AppleScript (Mac-only), a URL scheme, and an undocumented local SQLite database.

But the usual diagnosis is incomplete. The tools that exist today are thin wrappers: they expose
what the platform gives and stop there. None of them address what actually hurts once an AI agent
starts writing into your task list:

- you cannot tell whether a write **actually took effect**;
- there is no way to **undo** when it didn't;
- destructive operations don't know the task is **repeating**, and recurrence cannot be recreated
  by any API;
- a transient Apple Event error is indistinguishable from a real failure.

**This is not another wrapper.** The core is the guarantee layer that's missing.

## Capability matrix

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

Every cell has an exact, tested command in **[docs/PLAYBOOK.md](docs/PLAYBOOK.md)**.

## Findings you won't find elsewhere

| Finding | Why it matters |
|---|---|
| `checklist-items` works on `operation: update` and **replaces the whole list** | The only way to edit the text of an existing checklist item. Documented as create-only |
| `append-checklist-items` / `prepend-checklist-items` **do nothing** | Documented as working. Accepts the request, changes nothing, reports no error |
| A heading is addressable as `to do id "<uuid>"` | The only way to rename a heading, even though `heading` is not a class in the dictionary |
| Recurrence is a **binary plist** in `TMTask.rt1_recurrenceRule` | Readable. Still unwritable — which is exactly why a guard needs to read it |
| `open -g -j` keeps Things in the background | Without the flags, a closed Things steals the user's focus |
| `delete` is **asymmetric** | To-do and project go to the native Trash (reversible); area and tag are gone for good; heading fails |
| `move ... to` is typed as `list` | Moving a to-do to a *project* fails with `301`; use `set project of` instead |
| `sdef` requires full Xcode | With only Command Line Tools it returns **empty**, so `sdef … | grep X` becomes a silent false negative |

## What is guaranteed — and what isn't

**There are no transactions.** Things exposes nothing of the sort, and any project promising
"atomic operations" on top of it is overselling. What this library does guarantee:

- **dry-run by default** on anything destructive;
- a **backup** written before the write, with its path reported;
- **verification after the write**, by re-reading and comparing — because a success return code
  does not prove the operation had any effect;
- a **recurrence guard**: destructive operations on repeating tasks are refused, since recurrence
  cannot be recreated;
- **retries only for transient errors**, never for permanent ones;
- **per-item isolation** in batches: one failure does not take down the rest.

Not guaranteed: automatic rollback (the backup is deliberately manual — reverting blindly can make
things worse), atomicity across multiple items, and anything requiring recurrence to be writable.

## Install

```bash
git clone https://github.com/eualannascimento/things3-mapping-playbook.git
cd things3-mapping-playbook
python3 -m pytest tests/    # no runtime dependencies
```

Requires macOS with Things 3. Editing existing checklist items additionally needs an auth token
(Things → Settings → General → Enable Things URLs → Manage), read only from the environment:

```bash
export THINGS_AUTH_TOKEN="..."
```

## Start here

```bash
python3 -m things3.cli doctor
```

Most "it doesn't work" reports come down to a handful of causes, each producing an error far from
its root: automation permission never granted looks like a missing object; Things never launched
looks like a missing database; a token in `~/.zshrc` instead of `~/.zshenv` looks like an update
that silently did nothing. `doctor` names the cause and the fix.

```
  [  ok] Things 3 installed: version 3.22.11
  [  ok] Database readable: 549 rows in TMTask
  [  ok] AppleScript permission: granted
  [warn] THINGS_AUTH_TOKEN: not set (only needed to edit existing checklist items)
```

## CLI

Anything destructive is a dry run unless you pass `--apply`.

```bash
things3 show <uuid>                       # item + checklist + recurrence, all in one place
things3 checklist <uuid> --rename "Old=New"       # dry run
things3 checklist <uuid> --rename "Old=New" --apply
things3 delete todo <uuid> --apply        # native Trash, restorable
things3 delete area "Health" --by-name --apply --allow-irreversible
```

## Usage

```python
from things3 import read, ops, checklist

conn = read.connect()

# Read what AppleScript cannot see
items = read.checklist_items(conn, "task-uuid")
print(read.recurrence(conn, "task-uuid"))   # {'every': 1, 'unit': 'weekly', 'weekdays': [1, 3]}

# Everyday operations, with the guards applied
ops.create(ops.Kind.TODO, "Buy bread")
ops.move("task-uuid", to_project="Groceries")   # uses `set project of`, not the 301 trap
ops.delete(conn, ops.Kind.TODO, "task-uuid")    # native Trash, reversible
ops.restore(ops.Kind.TODO, "task-uuid")

# Fix a checklist item's text -- dry run first
plan = checklist.plan(conn, "task-uuid", rename={"Drink watre": "Drink water"})
print(plan.after)

# Apply: backs up, replaces the list, verifies against SQLite
checklist.apply(conn, plan)
```

The guards are not advisory — they refuse:

```python
ops.delete(conn, ops.Kind.TODO, "repeating-task-uuid")
# RecurrenceGuardError: recurrence cannot be recreated by any Things API

ops.delete(conn, ops.Kind.AREA, "Health")
# ConfirmationRequired: irreversible, does not go to the Trash

ops.delete(conn, ops.Kind.AREA, "Health", allow_irreversible=True)
# proceeds, and writes a backup of which items belonged to it first
```

## Docs

- **[docs/PLAYBOOK.md](docs/PLAYBOOK.md)** — the exact command for every type × action, plus the
  traps that cost the most to find
- **[docs/API-MAP.md](docs/API-MAP.md)** — full AppleScript dictionary inventory, what the API does
  not cover, and live test results
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — design decisions and their reasoning

## License

MIT
