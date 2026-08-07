# Changelog

This project makes claims about a closed application that can change under it. Corrections to
those claims matter as much as features, so both are recorded here.

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

### Fixed
- **`delete` replaced by `move … to list "Trash"` for to-dos and projects.** The live suite caught
  `delete (to do id "…")` failing intermittently with `-1728` on objects readable through the very
  same specifier moments earlier. Both routes send the item to the Trash; only one is reliable.
  This was a real bug in this library, found by the tests added in the same release.

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

### Corrections to the official documentation
- `checklist-items` is documented as create-only but works on `operation: update`, replacing the
  whole list. It is the only way to edit an existing checklist item.
- `append-checklist-items` and `prepend-checklist-items` are documented as working. They do
  nothing: the request is accepted, nothing changes, no error is reported.
