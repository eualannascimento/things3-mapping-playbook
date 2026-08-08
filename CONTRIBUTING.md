# Contributing

The value of this project is that its claims are true. One wrong cell in the capability matrix and
someone builds on a promise the platform does not keep. So the rules below are about evidence, not
style.

## The one rule

**A capability claim needs a live test.** If you add or change a cell in the matrix — turning a ❌
into a 🟡, adding a workaround, marking something irreversible — there must be a test in
`tests/live/` that reproduces it against a real Things install. "It worked when I tried it" is how
this project's own documentation ended up wrong twice.

Corollary: if you cannot run the live suite (no Mac, no Things), you can still contribute code,
docs and mocked tests — just say so in the PR, and don't change the matrix.

## Running the tests

```bash
pytest                         # mocked suite; no Things needed, runs in CI
pytest -m 'live and not i18n'  # talks to a real Things 3 install; opt-in
pytest -m i18n                 # also restarts Things and changes its language; opt-in
```

The live suite creates objects prefixed `zzlive-`, tracks every one, and a session-level sweep
**fails the run** if anything survives. A test suite that litters someone's task list is worse than
no test suite. If you add a live test, create objects through the `sandbox` fixture so they are
tracked — never build them directly.

Some live tests need `THINGS_AUTH_TOKEN` (anything using `operation: update`). They skip cleanly
without it. Export it from a file your non-interactive shell reads — `~/.zshenv`, not `~/.zshrc`.

Every live test declares the playbook recipe it reproduces:

```python
@pytest.mark.verifies("todo.delete", cell="todo/D", grade="✅")
```

The run writes its results to `VERIFIED.json`, which is committed. `first_verified` records when
the claim was first reproduced and is left alone for as long as it keeps passing, so a claim that
has held for months is distinguishable from one verified once and never revisited.

`tests/test_coverage_invariant.py` runs in CI and fails when a recipe has no test, when a test
claims a recipe that does not exist, when two tests claim one recipe, or when the README matrix
drifts from the ledger. Adding a recipe to the playbook without a test fails the build.

## Claiming something is impossible

`❌` means **no path exists, not even by composing operations**. Before marking a cell impossible,
try the compositions: rebuilding a parent object, moving instead of recreating, addressing an
object through a different class. Several cells that looked impossible turned out to be 🟡 or 🔶
only after someone tried the third or fourth variation.

If a sequence of supported steps reaches the result, it is 🟡 (cheap) or 🔶 (expensive) — never ❌.

## Things to know before writing automation code

These cost real time to discover. They are in [docs/PLAYBOOK.md](docs/PLAYBOOK.md) in full:

- A success return code proves nothing. Moving an area to the Trash returns success and does
  nothing at all. Verify by re-reading.
- `move ... to` is typed as `list`; use `set project of` / `set area of` for projects and areas.
- `delete (to do id "…")` fails intermittently with `-1728` on objects that read fine through the
  same specifier. `move … to list "Trash"` does the same thing and has never failed.
- `append-checklist-items` is a no-op: accepted, silently ineffective.
- Deleting while iterating a live collection fails partway through.
- `sdef` needs full Xcode; without it, it returns empty and every grep becomes a false negative.
- A heading does not receive `trashed=1` when its parent project is sent to the Trash. It becomes
  unreachable through the app, but the SQLite row persists — addressable by uuid, immune to
  `delete` and to moving to the Trash directly — until the Trash is actually emptied. If you write
  a live test that creates a heading, its residue outlives the test session; the sweep does not
  (and cannot) clean it up. This is a real cost of testing headings, not a bug in the sweep.
- A long, unattended live run can produce a transient failure the same operation does not show
  when run alone seconds later — the scripting bridge degrading under sustained load, the same
  phenomenon behind the `-1728` finding above. Re-running the specific test is the right response,
  not loosening the assertion.

## Reporting a behaviour change

Things updates can invalidate any claim here. If a live test starts failing, that is the system
working: open an issue with your Things version, the failing test, and its output. The failure
messages are written to say what the change would mean — for example,
`"append-checklist-items appears to work now; the docs and the matrix need updating"`.
