# Changelog

This project makes claims about a closed application that can change under it. Corrections to
those claims matter as much as features, so both are recorded here.

## [0.4.0]

### Added
- Live tests for the remaining 69 recipes the ledger had left pending: every to-do, project, area,
  tag, heading, checklist and application recipe in the playbook now has one, split into
  `tests/live/test_{todo,project,area,tag,heading,checklist,app}.py` plus `test_guarantees.py` for
  library behaviour that is not tied to a single recipe. 75 of 78 recipes are verified live; the
  other 3 are recorded `untestable` with a stated reason. The capability matrix is generated
  entirely from this — 43 of 47 cells now carry a grade a passing test actually supports.

### Fixed
- **`heading.duplicate` documented the wrong error code.** The playbook claimed `-1717`, copied
  from the to-do and project cases; a heading actually fails with `-10006`, because it is not
  addressed through its own class. Found by the live test that was supposed to just confirm the
  claim.
- **`ledger.merge()` resurrected a stale cell/grade after a test stopped naming one.** A recipe
  whose marker no longer set `cell`/`grade` kept the previous run's values instead of clearing
  them, which could paint the matrix with a grade no current test supports. Fixed, with a
  regression test.
- **`project_with_heading()` matched a heading by title alone**, with no `trashed = 0` filter and
  no scope to the project just created. A same-titled heading left over from an earlier run — see
  the finding below — could be picked up instead of the one the test just built, corrupting the
  assertion. Now scoped to the freshly created project's own uuid.

### Found, not fixed (recorded as verified limits)
- **A heading never receives `trashed = 1` when its parent project is sent to the Trash.** It
  becomes unreachable through the app, but the row persists in SQLite — still addressable by uuid,
  still immune to `delete` and to moving to the Trash directly — until the Trash is actually
  emptied, which this project's own rule forbids automation from ever doing. Every live test that
  exercises a heading leaves one inert, invisible row behind; confirmed by finding 40 of them
  accumulated from earlier sessions, and confirmed that emptying the Trash by hand does clear them.
- **A long, unattended live run can produce a transient failure the same operation does not show
  seconds later in isolation** — the scripting bridge degrading under sustained load, the same
  phenomenon behind the `-1728` finding in 0.3.0. Not a defect in this library; documented so a
  flaky-looking CI run is diagnosed correctly instead of chased with looser assertions.

## [0.3.0]

### Added
- Live test suite (`pytest -m live`), opt-in, that reproduces the capability matrix against a real
  Things install. Until now the "verified live" claim rested on trust; it is now auditable, and a
  Things update that changes behaviour will surface as a failing test.
- Session-level sweep that fails the run if the live suite leaves anything behind.
- `doctor` command and CLI.
- `ops` module: guarded create, rename, move, status, delete, restore and bulk delete.
- CI running the mocked suite on Python 3.10–3.13, plus a job that verifies the live suite still
  collects.
- `VERIFIED.json`: a committed record of which playbook recipes were reproduced live, when they
  were first verified, and against which Things and macOS versions. The capability matrix in the
  README is generated from it, so a claim cannot outlive the test behind it.
- Coverage invariant in the mocked suite (`tests/test_coverage_invariant.py`): a recipe without a
  test, a test claiming a recipe that does not exist, two tests claiming one recipe, or a matrix
  out of step with the ledger all fail the build.
- `things3/lists.py`, and an i18n suite (`pytest -m i18n`) that switches the language Things runs
  in to prove the library does not depend on it.

### Added (continued)
- Staleness detection on checklist writes: because the write replaces the whole list, a plan built
  from older state would silently discard anything changed in between. `apply()` now re-reads and
  aborts on mismatch, with `force=True` to override deliberately.

### Fixed
- **`delete` replaced by `move … to list "Trash"` for to-dos and projects.** The live suite caught
  `delete (to do id "…")` failing intermittently with `-1728` on objects readable through the very
  same specifier moments earlier. Both routes send the item to the Trash; only one is reliable.
  This was a real bug in this library, found by the tests added in the same release.
- **Built-in lists addressed by localized display name, not by id.** Things ships nine languages,
  and `list "Trash"` only resolves in English. Confirmed live, not assumed: switching Things to
  German, `list id "TMTrashListSource"` still resolved the Trash and returned its German name,
  while `list "Trash"` failed outright. Every delete, restore, and list-based move would have
  failed for a user running Things in German, Spanish, French, Italian, Japanese, Russian, or
  either Chinese variant. Fixed by addressing built-in lists through `things3/lists.py`.

### Changed
- Capability matrix uses CRUD initials and fits without horizontal scrolling. `Rename` and `Edit`
  merged into `U` — they were identical in every row.

## [0.1.0]

### Added
- Verified map of the AppleScript API, extracted from the installed app's own dictionary.
- Playbook with one tested command per type and action.
- SQLite reader, including recurrence decoding from its binary plist.
- AppleScript and URL scheme backends.
- Guarantee layer: backup, post-write verification, recurrence guard, classified retries.
- Checklist editing via full-list replacement.

### Behaviour that differs from the reference
- `checklist-items` is listed among create attributes, but works on `operation: update` and
  replaces the whole list. It is the only way to edit an existing checklist item.
- `append-checklist-items` and `prepend-checklist-items` are no-ops: the request is accepted,
  nothing changes, no error is reported.
