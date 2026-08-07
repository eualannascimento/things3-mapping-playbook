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
pytest                    # mocked suite; no Things needed, runs in CI
pytest -m live            # talks to a real Things 3 install; opt-in
```

The live suite creates objects prefixed `zzlive-`, tracks every one, and a session-level sweep
**fails the run** if anything survives. A test suite that litters someone's task list is worse than
no test suite. If you add a live test, create objects through the `sandbox` fixture so they are
tracked — never build them directly.

Some live tests need `THINGS_AUTH_TOKEN` (anything using `operation: update`). They skip cleanly
without it. Export it from a file your non-interactive shell reads — `~/.zshenv`, not `~/.zshrc`.

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
- `append-checklist-items` does nothing, despite being documented.
- Deleting while iterating a live collection fails partway through.
- `sdef` needs full Xcode; without it, it returns empty and every grep becomes a false negative.

## Reporting a behaviour change

Things updates can invalidate any claim here. If a live test starts failing, that is the system
working: open an issue with your Things version, the failing test, and its output. The failure
messages are written to say what the change would mean — for example,
`"append-checklist-items appears to work now; the docs and the matrix need updating"`.
