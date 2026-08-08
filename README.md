# things3-mapping-playbook

A verified map of what Things 3 automation can and cannot do — and the code to do it safely.

Everything here was executed against a real Things install (3.22.11, macOS 26.5) and verified by
re-reading the result, rather than taken from a reference. That distinction matters: on this
platform, **behaviour and documentation don't always line up**, in both directions — some things
described as available turn out to be no-ops, and some of the most useful capabilities aren't
described at all.

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

<!-- generated:matrix -->
| | C | R | U | D | Dup | Move | Done | Rest |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **To-do** | ✅ | ✅ | ✅ | ✅ | 🟡 | 🟡 | ✅ | ✅ |
| **Project** | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ |
| **Area** | ✅ | ✅ | ✅ | ⚠️ | 🟡 | ➖ | ➖ | 🔶 |
| **Tag** | ✅ | ✅ | ✅ | ⚠️ | 🟡 | ✅ | ➖ | 🔶 |
| **Heading** | 🟡 | 🟡 | 🟡 | 🔶 | 🔶 | 🔶 | ✅ | ➖ |
| **Checklist item** | ✅ | 🟡 | 🟡 | 🟡 | · | 🟡 | ✅ | ➖ |
| **Recurrence** | ❌ | 🟡 | · | · | ➖ | ➖ | ➖ | ➖ |
<!-- /generated:matrix -->

**Columns** — C create · R read · U update (rename and edit alike) · D delete · Dup duplicate ·
Move move · Done complete or cancel · Rest restore from the Trash

**Cells** — ✅ works directly · 🟡 cheap validated workaround · 🔶 expensive workaround (rebuild the
parent, or restore from a backup) · ⚠️ works but **irreversible** · ❌ impossible by any route,
including composition · ➖ not applicable · `·` no live test yet

Every cell has an exact, tested command in **[docs/PLAYBOOK.md](docs/PLAYBOOK.md)**.

## Findings you won't find elsewhere

| Finding | Why it matters |
|---|---|
| `checklist-items` works on `operation: update` and **replaces the whole list** | The only way to edit the text of an existing checklist item. Listed among create attributes, so easy to miss |
| `append-checklist-items` / `prepend-checklist-items` are **no-ops** | The request is accepted, nothing changes, no error is reported — so code using them fails silently |
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

- **staleness detection**: a checklist write compares against the state the plan was built on and
  aborts rather than clobbering an edit made in the app meanwhile.

Not guaranteed: automatic rollback (the backup is deliberately manual — reverting blindly can make
things worse), atomicity across multiple items, and anything requiring recurrence to be writable.

### Verified limits

| | |
|---|---|
| Scale | Read paths measured on a synthetic database of 10,000 tasks and 50,000 checklist items: full task read 16 ms, all checklist items 47 ms. No degradation to design around |
| Write latency | Creates and deletes appear in SQLite within milliseconds (median 3 ms, worst 45 ms over 15 samples), so verification does not need to wait |
| Concurrency | Only checklist writes are protected, since only they replace a whole structure. Field-level writes are last-write-wins, like the app itself |
| Things versions | Everything was verified on 3.22.11 / macOS 26.5. Older versions are untested; if a claim does not hold on yours, the live suite will say which one |
| Language | Built-in lists are addressed by stable id, not by localized name, so the library does not depend on the language Things runs in. Proven by `pytest -m i18n`, which switches the app's language and asserts both routes |
| Sustained load | A handful of tests in a 78-test back-to-back live run showed transient failures the app's scripting bridge did not show when run in isolation seconds later. Same phenomenon documented above for `delete`; individual operations are reliable, a long unattended automation run is not guaranteed to be |
| Heading residue | A heading never receives `trashed=1` when its parent project is sent to the Trash — it becomes unreachable through the app but the row persists in SQLite until the Trash is actually emptied, which no automation here ever does. A live suite that exercises headings leaves inert, invisible rows behind on every run |

## Install

```bash
git clone https://github.com/eualannascimento/things3-mapping-playbook.git
cd things3-mapping-playbook
pytest          # mocked suite, no Things needed, no runtime dependencies
pytest -m live  # reproduces the capability matrix against your real install
```

The live suite is how the claims above stay honest: it creates disposable objects, exercises the
real platform, and a sweep fails the run if anything is left behind. If a Things update changes
behaviour, a test breaks and says what it would mean.

Requires macOS with Things 3. Editing existing checklist items additionally needs an auth token
(Things → Settings → General → Enable Things URLs → Manage), read only from the environment:

```bash
export THINGS_AUTH_TOKEN="..."
```

### As a Claude Code skill

This repository is also a self-contained Claude Code skill: `SKILL.md` at the root describes when
to use it and how, wired to the same CLI documented below — no separate scripts, no duplicated
recipes. Clone it into `~/.claude/skills/` (or wherever your skills live) and `pip install -e .`
once; the skill instructs Claude to run `things3 <command>` for everyday operations and to consult
`docs/PLAYBOOK.md` for anything the CLI does not cover.

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

`checklist` and `delete` are dry runs unless you pass `--apply` -- the only two commands where
something could be lost. The rest write immediately: create, rename, move and status changes are
always reversible, so there is nothing to protect against.

```bash
things3 show <uuid>                       # item + checklist + recurrence, all in one place
things3 create todo "Buy bread"
things3 rename todo <uuid> "Buy bread and milk"
things3 move <uuid> --to-list Today       # or --to-project / --to-area
things3 status todo <uuid> completed
things3 restore todo <uuid>               # only to-dos and projects come back from the Trash
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
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — one rule: a capability claim needs a live test
- **[CHANGELOG.md](CHANGELOG.md)** — features and corrections to the claims, tracked equally

## License

MIT
