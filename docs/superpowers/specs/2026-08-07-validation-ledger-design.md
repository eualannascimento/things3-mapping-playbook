# Validation ledger and language portability — design

Date: 2026-08-07
Status: approved for planning

## Problem

The project asserts 78 recipes in `docs/PLAYBOOK.md` and 47 capability cells in `README.md`.
`CONTRIBUTING.md` states the project's one rule: *a capability claim needs a live test*. Seven
recipes have one. The remaining 71 rest on manual verification that no one can re-run.

Two consequences:

1. **Nothing records that a claim was validated.** There is no date, no Things version, no way to
   tell a claim verified last week from one verified in the first commit and never revisited.
2. **A Things update would silently invalidate most of the documentation.** The live suite would
   still pass, because it does not exercise what changed.

Separately, a portability defect was found while investigating: the library addresses Things'
built-in lists **by display name**, which is localized. Things ships nine languages. For a user
running it in German, Spanish, French, Italian, Japanese, Russian or Chinese, `move … to list
"Trash"` fails, and with it every delete this library performs.

## Goals

- Every recipe in the playbook is either backed by a live test that reproduces it, or explicitly
  recorded as untestable with the reason.
- A validated recipe is marked as such, with the date and environment, and is not revisited unless
  it fails.
- The library works regardless of the language the user runs Things in.
- Coverage cannot regress: adding a recipe without a test fails the build.

## Non-goals

- MCP server. Deferred deliberately; the base should be certified before a new surface is added.
- Older Things versions. Not reproducible on this machine or by contributors; recorded as a limit.
- Defensive code for conditions that cannot be exercised here. Untested defence is a claim, and
  claims are what this project exists to avoid.

## Design

### Unit of validation: the recipe

The capability matrix cell is too coarse. "Delete a to-do" is one cell but two independent
assertions — that it lands in the native Trash, and that it can be restored from there. Each gets
its own test.

Every playbook row gets a stable id derived from its section and action: `todo.delete`,
`heading.rename`, `tag.hierarchy`, `checklist.replace`. The id is written into the playbook row
itself, so the document and the tests share one vocabulary.

Each live test declares what it validates:

```python
@verifies("todo.delete")
def test_delete_sends_a_todo_to_the_native_trash(sandbox, conn):
    ...
```

One test, one recipe, one assertion of substance. A test that needs to assert three things is three
recipes that were collapsed into one row.

### The ledger

A pytest hook collects the outcome of every `@verifies` test and writes `VERIFIED.json`:

```json
{
  "environment": {"things": "3.22.11", "macos": "26.5", "python": "3.13.1"},
  "recipes": {
    "todo.delete": {
      "status": "pass",
      "test": "tests/live/test_todo.py::test_delete_sends_a_todo_to_the_native_trash",
      "first_verified": "2026-08-07",
      "last_verified": "2026-08-07"
    }
  }
}
```

`first_verified` is written once and never rewritten while the recipe keeps passing. That is what
"validated and frozen" means concretely: the test is re-executed, not rewritten, and the ledger
carries how long the claim has held. A failure is the only event that reopens a recipe.

Three status values:

| Status | Meaning |
|---|---|
| `pass` | Reproduced live in this environment |
| `fail` | Reproduced and did not hold — the claim is wrong or the platform changed |
| `untestable` | Cannot be exercised without a side effect outside the sandbox, with the reason recorded |

`untestable` is not an escape hatch. It is reserved for recipes whose execution is global and
destructive, and it must name why:

- `app.empty-trash` — irreversible and global; the project's own rule is never to call it
- `app.log-completed` — archives every completed item in the user's database, not just the sandbox
- `app.quick-entry` — takes over the user's screen; cannot run unattended

### Coverage as an invariant

A meta-test runs in the mocked suite (no Things required, so it runs in CI):

- parses `docs/PLAYBOOK.md` for recipe ids;
- collects every `@verifies` id in `tests/live/`;
- fails if a recipe has no test, if a test names a recipe that does not exist, or if two tests claim
  the same recipe.

This converts total coverage from a one-time effort into a property the repository maintains by
itself. Untestable recipes satisfy it via an explicit registry entry, not by omission.

### Documentation generated from the ledger

The capability matrix in `README.md` and the status markers in `docs/PLAYBOOK.md` are regenerated
from `VERIFIED.json` between HTML markers:

```
<!-- generated:matrix -->
… table …
<!-- /generated:matrix -->
```

Prose around the markers stays hand-written. A claim with no passing test cannot appear in a
generated block, which closes the gap that produced this spec.

### Language portability

New module `things3/lists.py` holding the built-in list ids, which are language-independent:

| List | Stable id |
|---|---|
| Inbox | `TMInboxListSource` |
| Today | `TMTodayListSource` |
| Anytime | `TMNextListSource` |
| Someday | `TMSomedayListSource` |
| Logbook | `TMLogbookListSource` |
| Trash | `TMTrashListSource` |

Every `list "Name"` reference becomes `list id "…"`: three in `things3/ops.py`, two in
`tests/live/conftest.py`, five recipes in the playbook.

The mapping and the `move … to list id "TMTrashListSource"` route were confirmed live before this
spec was written.

**Proving it, rather than asserting it.** A dedicated test module switches Things to another
language for the duration of the run:

```
defaults write com.culturedcode.ThingsMac AppleLanguages -array de
```

restarts the app, and asserts both directions: addressing by id still works, and addressing by the
English name now fails. Teardown restores the original `AppleLanguages` value and restarts the app,
and it must run even if the test fails.

This is the only test in the suite that changes machine state, so it lives in its own module behind
its own marker (`pytest -m i18n`), is excluded from the default live run, and refuses to start if
it cannot read the current setting to restore.

### Test isolation

Each test builds its own objects through the `sandbox` fixture and asserts one thing. The existing
session sweep already fails the run on leftovers; it keeps that role unchanged. Tests are grouped
into one module per type — `test_todo.py`, `test_project.py`, `test_area.py`, `test_tag.py`,
`test_heading.py`, `test_checklist.py`, `test_app.py` — replacing the single
`test_live_capabilities.py`, which at 78 recipes would become unreadable.

## Corrections included

| Item | Correction |
|---|---|
| `__version__` and `pyproject.toml` say `0.2.0`; `CHANGELOG.md` says `0.3.0` | Align on `0.3.0` and tag the release |
| The playbook still teaches `delete (to do id "…")` | Replace with the move-to-Trash route the library has used since the `-1728` finding |
| `doctor` does not detect the app's language or verify Trash access | Add a check that resolves the Trash by id and reports the localized name it found |

## Risks

| Risk | Mitigation |
|---|---|
| The i18n test leaves Things in another language if teardown is skipped | Refuse to start unless the original value was read; restore in a `finally`; a session-level check asserts the setting matches what it was |
| The live suite grows from ~66 s to several minutes | It is opt-in and not in CI. Per-type modules allow running one section |
| Some of the 71 recipes turn out to be wrong under isolated testing | That is the point. A recipe that fails is recorded `fail` and corrected in the playbook, as happened with `delete` |
| A generated documentation block is edited by hand and overwritten | The meta-test compares generated blocks against the ledger and fails on drift, so the loss is caught before it is committed |

## Success criteria

- `VERIFIED.json` covers all 78 recipes: `pass` or an `untestable` entry with a stated reason.
- The meta-test fails when a recipe loses its test, gains a duplicate, or drifts from the ledger.
- No `list "Name"` remains in library code or in the playbook.
- The i18n suite proves the by-name route breaks and the by-id route holds.
- The live suite still leaves nothing behind, and the machine's language setting is unchanged after
  it runs.
