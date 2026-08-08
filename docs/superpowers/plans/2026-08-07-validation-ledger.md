# Validation Ledger and Language Portability — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every capability claim in this repository backed by a live test whose result is recorded with its date and environment, and make the library work regardless of the language the user runs Things in.

**Architecture:** Recipe ids are derived deterministically from the playbook's own text, so the document and the tests share one vocabulary with no second registry to drift. Live tests declare which recipe they validate through a pytest marker; a session hook writes the outcomes to a committed `VERIFIED.json`. A meta-test in the mocked suite reconciles playbook, ledger and tests, and fails on any gap — which is what keeps coverage from regressing once it is achieved.

**Tech Stack:** Python 3.10+, pytest, stdlib only (no runtime dependencies), AppleScript via `osascript`, Things 3 URL scheme, SQLite read-only.

## Global Constraints

- **No runtime dependencies.** `pyproject.toml` declares `dependencies = []`. Test-only tooling may use pytest; library code may not import it.
- **Python floor is 3.10.** Use `X | None` unions, not `Optional[X]`.
- **The library never writes to SQLite.** Reads use `mode=ro` exclusively.
- **`THINGS_AUTH_TOKEN` is read from `os.environ` only.** Never a command-line argument, never written to any file in the repository.
- **Never call `empty trash`** from any code path, including tests.
- **Never create structure in the user's database** that Things does not already have — no control projects, no system tags or areas.
- **Live tests create objects through the `sandbox` fixture only**, so the session sweep can guarantee teardown. Objects built directly leak.
- **Branch is `validation-ledger`.** Never commit to `main`; the work lands through a PR.
- **Language of the repository is English.** Code, comments, docs and commit messages.

---

## File Structure

| File | Responsibility |
|---|---|
| `things3/lists.py` (create) | The built-in list ids, and the helper that produces a language-independent AppleScript specifier |
| `things3/verification/__init__.py` (create) | Package marker for the verification tooling |
| `things3/verification/recipes.py` (create) | Parse `docs/PLAYBOOK.md` into recipe ids. Single source of what claims exist |
| `things3/verification/ledger.py` (create) | Load, merge and save `VERIFIED.json`, preserving `first_verified` |
| `things3/verification/render.py` (create) | Regenerate the marked blocks in `README.md` from the ledger |
| `things3/ops.py` (modify) | Replace the three literal `list "Trash"` references with list ids |
| `things3/doctor.py` (modify) | Add a check that resolves the Trash by id and reports the localized name |
| `tests/live/conftest.py` (modify) | Register the `verifies` marker, collect outcomes, write the ledger, use list ids in teardown |
| `tests/live/test_i18n.py` (create) | Prove the by-name route breaks under another language and the by-id route holds |
| `tests/live/test_live_capabilities.py` (modify) | Add `verifies` markers to the seven existing tests |
| `tests/test_recipes.py` (create) | Unit tests for the parser, against a fixture playbook |
| `tests/test_ledger.py` (create) | Unit tests for merge semantics, especially `first_verified` |
| `tests/test_coverage_invariant.py` (create) | The meta-test: reconcile playbook, ledger and tests |
| `VERIFIED.json` (create) | The committed ledger |
| `docs/PLAYBOOK.md` (modify) | Correct the to-do delete recipe; use list ids in the five name-based recipes |
| `pyproject.toml` (modify) | Version `0.3.0`, ship the `things3.verification` subpackage |

---

### Task 1: Prove or disprove that list names are localized

This task comes first and changes no library code. The entire portability argument rests on an assumption that has not been tested: that Things returns localized list names to AppleScript. If it does not, there is no bug, and the claim must be retracted rather than the code changed.

**Files:**
- Create: `tests/live/test_i18n.py`

**Interfaces:**
- Consumes: `things3.applescript.run`, the `sandbox` and `conn` fixtures from `tests/live/conftest.py`
- Produces: nothing other tasks import. Its output is a recorded fact that decides Task 2's framing.

- [ ] **Step 1: Write the language-switching fixture and the test**

The fixture is the risky part, so it is written defensively: it refuses to run unless it can read the current setting well enough to restore it, and it restores in a `finally` that runs even when the test fails.

```python
"""Prove the library does not depend on the language Things runs in.

Things ships nine localizations. Built-in lists are addressed in AppleScript
either by display name -- which is localized -- or by a stable id, which is not.
This module switches the app's language for the duration of the run and asserts
both directions, because the alternative is asserting it from the documentation,
which is how this project's claims went wrong before.

It is the only test here that changes machine state, so it lives behind its own
marker and is excluded from the default live run.
"""
from __future__ import annotations

import subprocess
import time

import pytest

from things3 import applescript

pytestmark = [pytest.mark.live, pytest.mark.i18n]

DOMAIN = "com.culturedcode.ThingsMac"
KEY = "AppleLanguages"
TEST_LANGUAGE = "de"


def _read_languages() -> list[str] | None:
    """Current AppleLanguages for Things, or None when the key is unset."""
    result = subprocess.run(
        ["defaults", "read", DOMAIN, KEY],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return [
        line.strip().strip('",')
        for line in result.stdout.splitlines()
        if line.strip() not in ("(", ")")
    ]


def _write_languages(languages: list[str] | None) -> None:
    if languages is None:
        subprocess.run(["defaults", "delete", DOMAIN, KEY], capture_output=True)
    else:
        subprocess.run(
            ["defaults", "write", DOMAIN, KEY, "-array", *languages],
            capture_output=True, check=True,
        )


def _restart_things(timeout: float = 30.0) -> None:
    subprocess.run(
        ["osascript", "-e", 'tell application "Things3" to quit'],
        capture_output=True,
    )
    time.sleep(3)
    subprocess.run(["open", "-g", "-j", "-a", "Things3"], check=True)

    deadline = time.time() + timeout
    while time.time() < deadline:
        if applescript.run("  return name").ok:
            time.sleep(2)
            return
        time.sleep(1)
    raise RuntimeError("Things did not become reachable again after restart")


@pytest.fixture
def things_in_german():
    """Run Things in German, then put the setting back exactly as it was."""
    original = _read_languages()
    if original is not None and not original:
        pytest.skip("AppleLanguages is set but unreadable; refusing to risk the restore")

    try:
        _write_languages([TEST_LANGUAGE])
        _restart_things()
        yield
    finally:
        _write_languages(original)
        _restart_things()


def test_list_names_are_localized_but_ids_are_not(things_in_german):
    """The fact the whole portability argument depends on."""
    by_id = applescript.run('  return name of list id "TMTrashListSource"')
    assert by_id.ok, "the Trash must stay addressable by id in any language"
    assert by_id.stdout.strip() != "Trash", (
        f"Things returned {by_id.stdout.strip()!r} for the Trash while running in German. "
        "If this is still 'Trash', AppleScript list names are NOT localized, there is no "
        "portability bug, and the claim in the spec must be retracted."
    )


def test_addressing_the_trash_by_english_name_fails_in_german(things_in_german, sandbox):
    task = sandbox.todo("i18n")
    sandbox.settle()

    by_name = applescript.run(f'  move (to do id "{task}") to list "Trash"')
    assert not by_name.ok, "addressing by English name unexpectedly worked in German"


def test_addressing_the_trash_by_id_works_in_german(things_in_german, sandbox, conn):
    task = sandbox.todo("i18n-id")
    sandbox.settle()

    by_id = applescript.run(f'  move (to do id "{task}") to list id "TMTrashListSource"')
    assert by_id.ok, by_id.stderr
    sandbox.settle()
    assert conn.execute(
        "SELECT trashed FROM TMTask WHERE uuid=?", (task,)
    ).fetchone()[0] == 1
```

- [ ] **Step 2: Register the marker and keep it out of the default run**

Modify `pyproject.toml`, replacing the existing `[tool.pytest.ini_options]` block:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
# The live suite talks to a real Things install and is opt-in: `pytest -m live`.
# The i18n suite additionally restarts Things and changes its language setting,
# so it is excluded even from a live run unless asked for by name.
addopts = "-m 'not live and not i18n'"
markers = [
    "live: talks to a real Things 3 install (opt-in, macOS only)",
    "i18n: temporarily changes the language Things runs in (opt-in, restarts the app)",
]
```

Note the live suite is now selected with `pytest -m 'live and not i18n'`. Update `CONTRIBUTING.md` and `README.md` in Task 7, not here.

- [ ] **Step 3: Run the i18n suite and record the outcome**

Run: `cd /Users/eualannascimento/Development/things3-mapping-playbook && python3 -m pytest -m i18n -v`

Expected: takes about a minute, because it restarts Things twice.

There are two acceptable outcomes and both are results, not failures of the work:

- **All three pass** — list names are localized. The portability defect is real; proceed to Task 2 as a bug fix.
- **`test_list_names_are_localized_but_ids_are_not` fails** — names are not localized. There is no defect. Proceed to Task 2 anyway (addressing by id is still the more robust route), but the framing in the spec, the changelog and the commit message must say *hardening*, not *bug fix*, and the spec's Problem section must be corrected.

- [ ] **Step 4: Verify the machine was left as it was found**

Run: `defaults read com.culturedcode.ThingsMac AppleLanguages; echo "exit=$?"`

Expected: the same value as before the run, or `exit=1` if the key was unset originally. If it shows `de`, the teardown failed — restore manually with `defaults delete com.culturedcode.ThingsMac AppleLanguages` and fix the fixture before continuing.

- [ ] **Step 5: Commit**

```bash
git add tests/live/test_i18n.py pyproject.toml
git commit -m "Test whether Things localizes list names, rather than assuming it"
```

---

### Task 2: Address built-in lists by id

**Files:**
- Create: `things3/lists.py`
- Create: `tests/test_lists.py`
- Modify: `things3/ops.py` (the three `list "Trash"` references and the `to_list` parameter)
- Modify: `tests/live/conftest.py` (two teardown references)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `things3.lists.TRASH`, `INBOX`, `TODAY`, `ANYTIME`, `SOMEDAY`, `LOGBOOK` — `str` constants holding the stable ids
  - `things3.lists.specifier(list_id: str) -> str` — returns the AppleScript fragment `list id "…"`
  - `things3.lists.BY_ENGLISH_NAME: dict[str, str]` — maps the English display name to its id, so callers holding a name can migrate

- [ ] **Step 1: Write the failing test**

Create `tests/test_lists.py`:

```python
"""The list ids are the reason this library works in any language."""
import re

import pytest

from things3 import lists, ops


def test_specifier_addresses_by_id_not_by_name():
    assert lists.specifier(lists.TRASH) == 'list id "TMTrashListSource"'


def test_english_names_map_to_ids():
    assert lists.BY_ENGLISH_NAME["Trash"] == lists.TRASH
    assert lists.BY_ENGLISH_NAME["Anytime"] == lists.ANYTIME


def test_no_library_code_addresses_a_list_by_name():
    """A literal `list "Name"` is a defect: display names are localized."""
    from pathlib import Path

    package = Path(lists.__file__).parent
    offenders = []
    for path in package.rglob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r'list\s+"(?!\s*\{)', line) and "list id" not in line:
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert not offenders, "address these by id instead:\n" + "\n".join(offenders)
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python3 -m pytest tests/test_lists.py -v`

Expected: collection error, `ModuleNotFoundError: No module named 'things3.lists'`.

- [ ] **Step 3: Write the module**

Create `things3/lists.py`:

```python
"""Things' built-in lists, addressed by id rather than by name.

A list's `name` is what the user sees, and it is localized -- Things ships nine
languages. Its `id` is not: the same `TMTrashListSource` identifies the Trash
whichever language the app runs in. Addressing by name is therefore a defect
that only shows up on someone else's machine, which is the worst kind.

The ids were read from a real install with `name of every list` alongside
`id of every list`; the two lists correspond positionally.
"""
from __future__ import annotations

INBOX = "TMInboxListSource"
TODAY = "TMTodayListSource"
ANYTIME = "TMNextListSource"
SOMEDAY = "TMSomedayListSource"
LOGBOOK = "TMLogbookListSource"
TRASH = "TMTrashListSource"

#: English display name -> stable id, for callers migrating from names.
BY_ENGLISH_NAME = {
    "Inbox": INBOX,
    "Today": TODAY,
    "Anytime": ANYTIME,
    "Someday": SOMEDAY,
    "Logbook": LOGBOOK,
    "Trash": TRASH,
}


def specifier(list_id: str) -> str:
    """The AppleScript fragment addressing a built-in list.

    Ids are constants defined in this module and never user input, so they are
    interpolated directly; nothing here escapes attacker-controlled text.
    """
    return f'list id "{list_id}"'
```

- [ ] **Step 4: Run the test to see which offenders remain**

Run: `python3 -m pytest tests/test_lists.py -v`

Expected: the first two pass; `test_no_library_code_addresses_a_list_by_name` fails listing `ops.py:65`, `ops.py:128`, `ops.py:208` and `ops.py:263`.

- [ ] **Step 5: Migrate `ops.py`**

In `things3/ops.py`, add `lists` to the existing relative import, then:

Replace the body of `_trash_statement` (currently at `things3/ops.py:65`):

```python
        return f"  move ({spec}) to {lists.specifier(lists.TRASH)}"
```

At `things3/ops.py:263`, inside `delete_many`:

```python
        (uuid, f'move ({spec_kind} id "{applescript.escape(uuid)}") '
               f"to {lists.specifier(lists.TRASH)}")
```

The two remaining references (`things3/ops.py:128` and `things3/ops.py:208`) take a caller-supplied `to_list`. Change both functions to accept a list **id** instead of a name, keeping backwards compatibility for anyone passing an English name:

```python
def _list_specifier(to_list: str) -> str:
    """Accept either a stable id or an English display name.

    Passing a name still works, because it is what the previous version
    documented, but it resolves to the id -- so the call stops depending on the
    language the user runs Things in.
    """
    return lists.specifier(lists.BY_ENGLISH_NAME.get(to_list, to_list))
```

and use `f"  move ({spec}) to {_list_specifier(to_list)}"` in both places.

- [ ] **Step 6: Add the compatibility test**

Append to `tests/test_lists.py`:

```python
def test_a_caller_passing_an_english_name_still_reaches_the_id():
    assert ops._list_specifier("Anytime") == 'list id "TMNextListSource"'


def test_a_caller_passing_an_id_is_left_alone():
    assert ops._list_specifier(lists.TODAY) == 'list id "TMTodayListSource"'
```

- [ ] **Step 7: Run the whole mocked suite**

Run: `python3 -m pytest -v`

Expected: all pass. `tests/test_ops.py` asserts on generated AppleScript; any test asserting the literal `list "Trash"` must be updated to `list id "TMTrashListSource"` — that is a correct test change, not a weakened assertion.

- [ ] **Step 8: Migrate the live teardown**

In `tests/live/conftest.py`, both teardown paths build `move (…) to list "Trash"` (lines 56 and 140). Import `lists` and use `f'  try\n    move ({spec} id "{uuid}") to {lists.specifier(lists.TRASH)}\n  end try'` in both.

- [ ] **Step 9: Run the live suite**

Run: `python3 -m pytest -m 'live and not i18n' -v`

Expected: all pass, and the session sweep reports nothing left behind.

- [ ] **Step 10: Commit**

```bash
git add things3/lists.py things3/ops.py tests/test_lists.py tests/live/conftest.py tests/test_ops.py
git commit -m "Address built-in lists by stable id, not by localized name"
```

---

### Task 3: Derive recipe ids from the playbook

**Files:**
- Create: `things3/verification/__init__.py`
- Create: `things3/verification/recipes.py`
- Create: `tests/test_recipes.py`
- Modify: `pyproject.toml` (ship the subpackage)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `things3.verification.recipes.parse(path: Path) -> dict[str, str]` — recipe id → the action text it came from, in document order
  - `things3.verification.recipes.PLAYBOOK` — `Path` to `docs/PLAYBOOK.md`, resolved relative to the package
  - `things3.verification.recipes.DuplicateRecipeError` — raised when two rows produce the same id

- [ ] **Step 1: Write the failing test**

Create `tests/test_recipes.py`:

```python
"""The playbook is the single source of what this project claims."""
from pathlib import Path

import pytest

from things3.verification import recipes


@pytest.fixture
def playbook(tmp_path) -> Path:
    path = tmp_path / "PLAYBOOK.md"
    path.write_text(
        "# Playbook\n\n"
        "## Notation\n\n"
        "| | Meaning |\n|---|---|\n| `AS:` | AppleScript |\n\n"
        "## To-do\n\n"
        "| Action | Recipe |\n|---|---|\n"
        '| **Read** (one) | `AS: return name of to do id "<uuid>"` |\n'
        "| **Delete** | `AS: move to the Trash` |\n\n"
        "## Checklist item\n\n"
        "| Action | Recipe |\n|---|---|\n"
        "| **Limit** | 100 items per to-do |\n",
        encoding="utf-8",
    )
    return path


def test_ids_combine_section_and_action(playbook):
    assert list(recipes.parse(playbook)) == [
        "todo.read-one", "todo.delete", "checklist.limit"
    ]


def test_the_action_text_is_kept_for_reporting(playbook):
    assert recipes.parse(playbook)["todo.read-one"] == "Read (one)"


def test_rows_outside_a_known_section_are_ignored(playbook):
    """The Notation table is documentation, not a claim."""
    assert not any(rid.startswith("notation") for rid in recipes.parse(playbook))


def test_duplicate_ids_are_refused(tmp_path):
    path = tmp_path / "P.md"
    path.write_text(
        "## Tag\n\n| Action | Recipe |\n|---|---|\n"
        "| **Create** | `AS: a` |\n| **Create** | `AS: b` |\n",
        encoding="utf-8",
    )
    with pytest.raises(recipes.DuplicateRecipeError, match="tag.create"):
        recipes.parse(path)


def test_the_real_playbook_parses_to_unique_ids():
    parsed = recipes.parse(recipes.PLAYBOOK)
    assert len(parsed) == 78, f"the playbook now claims {len(parsed)} recipes"
    assert "todo.delete" in parsed
    assert "app.empty-the-trash" in parsed
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python3 -m pytest tests/test_recipes.py -v`

Expected: `ModuleNotFoundError: No module named 'things3.verification'`.

- [ ] **Step 3: Write the parser**

Create `things3/verification/__init__.py`:

```python
"""Tooling that keeps this project's claims tied to tests that reproduce them.

Shipped with the package rather than kept aside, because the ledger is part of
what this project offers: a reader can check when a claim was last verified and
against which Things version.
"""
```

Create `things3/verification/recipes.py`:

```python
"""Turn the playbook into a set of recipe ids.

The id is derived from the document rather than written into it, so there is no
second registry to fall out of sync. Rename an action and its id changes, which
breaks the test that claims it -- loudly, which is the point.
"""
from __future__ import annotations

import re
from pathlib import Path

PLAYBOOK = Path(__file__).resolve().parents[2] / "docs" / "PLAYBOOK.md"

#: Only these sections hold capability claims. Anything else is prose.
SECTION_SLUGS = {
    "To-do": "todo",
    "Project": "project",
    "Area": "area",
    "Tag": "tag",
    "Heading": "heading",
    "Checklist item": "checklist",
    "Application": "app",
}

_SECTION = re.compile(r"^##\s+(.*?)\s*$")


class DuplicateRecipeError(ValueError):
    """Two rows produced the same id, so one of them could never be tested."""


def _slug(text: str) -> str:
    text = re.sub(r"[*`]", "", text).strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def parse(path: Path | None = None) -> dict[str, str]:
    """Map recipe id -> action text, in document order."""
    path = path or PLAYBOOK
    section: str | None = None
    found: dict[str, str] = {}

    for line in path.read_text(encoding="utf-8").splitlines():
        heading = _SECTION.match(line)
        if heading:
            section = SECTION_SLUGS.get(heading.group(1))
            continue
        if section is None or not line.startswith("| **"):
            continue

        action = re.sub(r"[*`]", "", line.split("|")[1]).strip()
        recipe_id = f"{section}.{_slug(action)}"
        if recipe_id in found:
            raise DuplicateRecipeError(
                f"{recipe_id} appears twice in {path.name}; "
                "two rows with the same action cannot be validated separately"
            )
        found[recipe_id] = action

    return found
```

- [ ] **Step 4: Ship the subpackage**

In `pyproject.toml`, replace the `[tool.setuptools]` block:

```toml
[tool.setuptools]
packages = ["things3", "things3.verification"]
```

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest tests/test_recipes.py -v`

Expected: all six pass, including `test_the_real_playbook_parses_to_unique_ids` reporting 78.

- [ ] **Step 6: Commit**

```bash
git add things3/verification/ tests/test_recipes.py pyproject.toml
git commit -m "Derive recipe ids from the playbook itself, so nothing can drift"
```

---

### Task 4: Record what was verified, and when

**Files:**
- Create: `things3/verification/ledger.py`
- Create: `tests/test_ledger.py`
- Modify: `tests/live/conftest.py` (marker registration, outcome collection, session write)
- Modify: `tests/live/test_live_capabilities.py` (mark the seven existing tests)
- Create: `VERIFIED.json` (produced by the first live run, then committed)

**Interfaces:**
- Consumes: `things3.verification.recipes.parse`
- Produces:
  - `things3.verification.ledger.Ledger` — dataclass with `environment: dict`, `recipes: dict[str, dict]`, `untestable: dict[str, str]`, `pending: list[str]`
  - `things3.verification.ledger.load(path: Path | None = None) -> Ledger`
  - `things3.verification.ledger.save(ledger: Ledger, path: Path | None = None) -> None`
  - `things3.verification.ledger.merge(existing: Ledger, results: dict[str, dict], environment: dict, today: str) -> Ledger`
  - `things3.verification.ledger.LEDGER` — `Path` to `VERIFIED.json`
  - `things3.verification.ledger.UNTESTABLE` — the three global/destructive recipes and their reasons

- [ ] **Step 1: Write the failing test**

Create `tests/test_ledger.py`:

```python
"""What 'validated' means concretely: a date that stops moving once it is set."""
import json

import pytest

from things3.verification import ledger


@pytest.fixture
def existing():
    return ledger.Ledger(
        environment={"things": "3.22.11", "macos": "26.5", "python": "3.13.1"},
        recipes={"todo.delete": {
            "status": "pass", "test": "tests/live/test_todo.py::test_delete",
            "first_verified": "2026-08-01", "last_verified": "2026-08-01",
        }},
        untestable={},
        pending=["todo.rename"],
    )


def _result(status="pass", test="tests/live/test_todo.py::test_delete"):
    return {"status": status, "test": test}


def test_a_passing_recipe_keeps_its_original_first_verified(existing):
    merged = ledger.merge(existing, {"todo.delete": _result()},
                          existing.environment, today="2026-09-15")
    assert merged.recipes["todo.delete"]["first_verified"] == "2026-08-01"
    assert merged.recipes["todo.delete"]["last_verified"] == "2026-09-15"


def test_a_newly_passing_recipe_gets_both_dates(existing):
    merged = ledger.merge(existing, {"todo.rename": _result(test="t::r")},
                          existing.environment, today="2026-09-15")
    assert merged.recipes["todo.rename"]["first_verified"] == "2026-09-15"


def test_a_newly_passing_recipe_leaves_pending(existing):
    merged = ledger.merge(existing, {"todo.rename": _result(test="t::r")},
                          existing.environment, today="2026-09-15")
    assert "todo.rename" not in merged.pending


def test_a_failure_resets_first_verified(existing):
    """A claim that stopped holding is not a claim that has held since August."""
    merged = ledger.merge(existing, {"todo.delete": _result(status="fail")},
                          existing.environment, today="2026-09-15")
    assert merged.recipes["todo.delete"]["status"] == "fail"
    assert merged.recipes["todo.delete"]["first_verified"] is None


def test_a_skipped_recipe_does_not_touch_what_was_already_verified(existing):
    """Skipping for a missing token must not erase a real verification."""
    merged = ledger.merge(existing, {"todo.delete": _result(status="skip")},
                          existing.environment, today="2026-09-15")
    assert merged.recipes["todo.delete"]["last_verified"] == "2026-08-01"


def test_a_skipped_recipe_never_enters_the_ledger(existing):
    merged = ledger.merge(existing, {"todo.rename": _result(status="skip", test="t::r")},
                          existing.environment, today="2026-09-15")
    assert "todo.rename" not in merged.recipes
    assert "todo.rename" in merged.pending


def test_round_trip_through_disk(existing, tmp_path):
    path = tmp_path / "VERIFIED.json"
    ledger.save(existing, path)
    assert json.loads(path.read_text())["recipes"]["todo.delete"]["status"] == "pass"
    assert ledger.load(path).recipes == existing.recipes


def test_load_returns_an_empty_ledger_when_the_file_is_absent(tmp_path):
    empty = ledger.load(tmp_path / "nope.json")
    assert empty.recipes == {} and empty.pending == []
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python3 -m pytest tests/test_ledger.py -v`

Expected: `ImportError: cannot import name 'ledger'`.

- [ ] **Step 3: Write the ledger**

Create `things3/verification/ledger.py`:

```python
"""The record of which claims were reproduced, when, and against what.

`first_verified` is the point of this file. It is written once and left alone
for as long as the recipe keeps passing, so a reader can tell a claim that has
held for months from one verified in the first commit and never revisited. A
failure clears it, because a claim that stopped holding has not held since.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[2] / "VERIFIED.json"

#: Recipes that cannot be exercised without a side effect outside the sandbox.
#: This is not an escape hatch -- each entry states why, and only global or
#: destructive commands qualify.
UNTESTABLE = {
    "app.empty-the-trash":
        "irreversible and global; this project's own rule is never to call it",
    "app.archive-completed":
        "archives every completed item in the user's database, not just the sandbox",
    "app.quick-entry-panel":
        "takes over the user's screen; cannot run unattended",
}


@dataclass
class Ledger:
    environment: dict = field(default_factory=dict)
    recipes: dict[str, dict] = field(default_factory=dict)
    untestable: dict[str, str] = field(default_factory=dict)
    pending: list[str] = field(default_factory=list)


def load(path: Path | None = None) -> Ledger:
    path = path or LEDGER
    if not path.exists():
        return Ledger()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Ledger(
        environment=raw.get("environment", {}),
        recipes=raw.get("recipes", {}),
        untestable=raw.get("untestable", {}),
        pending=raw.get("pending", []),
    )


def save(ledger: Ledger, path: Path | None = None) -> None:
    path = path or LEDGER
    payload = {
        "environment": ledger.environment,
        "untestable": ledger.untestable,
        "pending": sorted(ledger.pending),
        "recipes": dict(sorted(ledger.recipes.items())),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def merge(existing: Ledger, results: dict[str, dict], environment: dict,
          today: str) -> Ledger:
    """Fold one run's results into the ledger.

    `results` maps recipe id -> {"status": "pass"|"fail"|"skip", "test": nodeid}.
    A skip is not evidence in either direction, so it is dropped entirely.
    """
    recipes = dict(existing.recipes)
    pending = list(existing.pending)

    for recipe_id, result in results.items():
        if result["status"] == "skip":
            continue

        previous = recipes.get(recipe_id, {})
        if result["status"] == "pass":
            first = previous.get("first_verified") or today
        else:
            first = None

        recipes[recipe_id] = {
            "status": result["status"],
            "test": result["test"],
            "first_verified": first,
            "last_verified": today,
        }
        if recipe_id in pending:
            pending.remove(recipe_id)

    return Ledger(environment=environment, recipes=recipes,
                  untestable=dict(existing.untestable), pending=pending)
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_ledger.py -v`

Expected: all eight pass.

- [ ] **Step 5: Collect outcomes from the live run**

Append to `tests/live/conftest.py`:

```python
_RESULTS: dict[str, dict] = {}


def _environment() -> dict:
    """What the ledger's claims are true of."""
    import subprocess
    import sys

    version = subprocess.run(
        ["/usr/libexec/PlistBuddy", "-c", "Print :CFBundleShortVersionString",
         "/Applications/Things3.app/Contents/Info.plist"],
        capture_output=True, text=True,
    ).stdout.strip()
    return {
        "things": version or "unknown",
        "macos": platform.mac_ver()[0],
        "python": f"{sys.version_info.major}.{sys.version_info.minor}."
                  f"{sys.version_info.micro}",
    }


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    marker = item.get_closest_marker("verifies")
    if marker is None or report.when != "call":
        return
    if report.skipped:
        status = "skip"
    else:
        status = "pass" if report.passed else "fail"
    _RESULTS[marker.args[0]] = {"status": status, "test": item.nodeid}


def pytest_sessionfinish(session, exitstatus):
    if not _RESULTS:
        return
    from datetime import date

    from things3.verification import ledger as ledger_module

    current = ledger_module.load()
    if not current.untestable:
        current.untestable = dict(ledger_module.UNTESTABLE)
    merged = ledger_module.merge(
        current, _RESULTS, _environment(), today=date.today().isoformat()
    )
    ledger_module.save(merged)
```

Also register the marker inside the existing `pytest_configure`:

```python
    config.addinivalue_line(
        "markers",
        "verifies(recipe, cell=None, grade=None): the playbook recipe this test reproduces",
    )
```

- [ ] **Step 6: Mark the seven existing tests**

In `tests/live/test_live_capabilities.py`, add a marker above each test. The `cell` and `grade` arguments feed the generated matrix in Task 6; a test that validates a recipe with no matrix cell passes neither.

```python
@pytest.mark.verifies("todo.move-to-a-project", cell="todo/Move", grade="🟡")
def test_move_to_project_needs_set_not_move(sandbox, conn):

@pytest.mark.verifies("todo.delete", cell="todo/D", grade="✅")
def test_delete_sends_todo_to_the_trash_and_restore_brings_it_back(sandbox, conn):

@pytest.mark.verifies("checklist.rename-edit-an-item", cell="checklist/U", grade="🟡")
def test_checklist_replacement_preserves_order_and_completed_state(sandbox, conn):

@pytest.mark.verifies("checklist.append-to-an-existing-to-do")
def test_append_checklist_items_does_nothing(sandbox, conn):

@pytest.mark.verifies("heading.rename", cell="heading/U", grade="🟡")
def test_heading_is_addressable_as_a_todo_and_can_be_renamed(sandbox, conn):

@pytest.mark.verifies("heading.delete", cell="heading/D", grade="🔶")
def test_heading_cannot_be_deleted(sandbox, conn):

@pytest.mark.verifies("area.move-to-trash")
def test_verification_catches_a_silent_no_op(sandbox, conn):
```

`test_deleting_while_iterating_the_live_collection_fails`, `test_recurrence_guard_refuses_a_real_repeating_task`, `test_accents_and_multiline_notes_survive_a_round_trip` and `test_stale_plan_is_refused_against_a_real_edit` stay unmarked: they test library behaviour, not a playbook recipe.

Note `test_delete_sends_todo_to_the_trash_and_restore_brings_it_back` covers two recipes at once. Split it, so `todo.restore` gets its own test — the spec's rule is one test, one recipe:

```python
@pytest.mark.verifies("todo.restore", cell="todo/Rest", grade="✅")
def test_restore_brings_a_trashed_todo_back(sandbox, conn):
    task = sandbox.todo()
    sandbox.settle()
    ops.delete(conn, ops.Kind.TODO, task)
    sandbox.settle()

    ops.restore(ops.Kind.TODO, task)
    sandbox.settle()
    assert conn.execute(
        "SELECT trashed FROM TMTask WHERE uuid=?", (task,)
    ).fetchone()[0] == 0
```

and trim the delete test to assert only `trashed == 1`.

- [ ] **Step 7: Seed the pending list**

Run this once to write the initial ledger, listing everything not yet covered:

```bash
python3 - <<'PY'
from things3.verification import ledger, recipes
known = set(recipes.parse())
current = ledger.load()
current.untestable = dict(ledger.UNTESTABLE)
current.pending = sorted(known - set(current.recipes) - set(current.untestable))
ledger.save(current)
print(f"{len(known)} recipes: {len(current.recipes)} verified, "
      f"{len(current.untestable)} untestable, {len(current.pending)} pending")
PY
```

Expected: `78 recipes: 0 verified, 3 untestable, 75 pending`.

- [ ] **Step 8: Run the live suite and check the ledger filled in**

Run: `python3 -m pytest -m 'live and not i18n' -v && python3 -c "
from things3.verification import ledger
l = ledger.load()
print(len(l.recipes), 'verified;', len(l.pending), 'pending')
print(l.environment)
"`

Expected: 8 verified (the seven marked plus the split restore test), 67 pending, and an environment block naming your Things and macOS versions. Recipes needing `THINGS_AUTH_TOKEN` will show as skipped and stay pending if the token is not exported.

- [ ] **Step 9: Commit**

```bash
git add things3/verification/ledger.py tests/test_ledger.py tests/live/conftest.py \
        tests/live/test_live_capabilities.py VERIFIED.json
git commit -m "Record which claims were reproduced, when, and against what"
```

---

### Task 5: Make coverage an invariant

**Files:**
- Create: `tests/test_coverage_invariant.py`

**Interfaces:**
- Consumes: `things3.verification.recipes.parse`, `things3.verification.ledger.load`
- Produces: nothing other tasks import. It is the gate.

This test runs in the mocked suite, so it runs in CI where no Things install exists. It reads the committed ledger rather than running anything.

- [ ] **Step 1: Write the test**

Create `tests/test_coverage_invariant.py`:

```python
"""Reconcile the playbook, the ledger and the tests. This is the gate.

The project's stated rule is that a capability claim needs a live test. Before
this test existed, that was a policy in a document; now a claim without a test
fails the build.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from things3.verification import ledger, recipes

LIVE_TESTS = Path(__file__).parent / "live"

#: The recipes still waiting for a test. This number may only ever go DOWN.
#: Raising it means a claim was added without a test, which is the thing this
#: file exists to prevent.
#:
#: Set this to whatever `len(ledger.load().pending)` reports after the live run
#: in Task 4 -- 67 if THINGS_AUTH_TOKEN was exported, higher if the checklist
#: tests skipped for want of it. Record the number you actually observed; do not
#: copy the one written here.
MAX_PENDING = 67


def _claimed_recipes() -> list[tuple[str, str]]:
    """(recipe id, test file) for every @pytest.mark.verifies in the live suite.

    Parsed rather than collected, so this works with no Things installed.
    """
    claims = []
    for path in LIVE_TESTS.glob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                target = decorator.func
                if (isinstance(target, ast.Attribute) and target.attr == "verifies"
                        and decorator.args):
                    claims.append((ast.literal_eval(decorator.args[0]), path.name))
    return claims


def test_every_recipe_is_accounted_for():
    """Verified, untestable or pending -- nothing may be simply absent."""
    known = set(recipes.parse())
    current = ledger.load()
    accounted = set(current.recipes) | set(current.untestable) | set(current.pending)
    assert known - accounted == set(), (
        "these recipes are in the playbook but nowhere in the ledger: "
        f"{sorted(known - accounted)}"
    )


def test_the_ledger_claims_nothing_the_playbook_does_not():
    known = set(recipes.parse())
    current = ledger.load()
    accounted = set(current.recipes) | set(current.untestable) | set(current.pending)
    assert accounted - known == set(), (
        "these ledger entries have no playbook recipe -- renamed or removed? "
        f"{sorted(accounted - known)}"
    )


def test_every_test_claims_a_recipe_that_exists():
    known = set(recipes.parse())
    unknown = [(rid, where) for rid, where in _claimed_recipes() if rid not in known]
    assert not unknown, f"tests claiming recipes that do not exist: {unknown}"


def test_no_recipe_is_claimed_by_two_tests():
    seen: dict[str, str] = {}
    clashes = []
    for recipe_id, where in _claimed_recipes():
        if recipe_id in seen:
            clashes.append(f"{recipe_id}: {seen[recipe_id]} and {where}")
        seen[recipe_id] = where
    assert not clashes, "one recipe, one test:\n" + "\n".join(clashes)


def test_a_verified_recipe_is_not_also_pending():
    current = ledger.load()
    both = set(current.recipes) & set(current.pending)
    assert not both, f"verified yet still listed as pending: {sorted(both)}"


def test_untestable_recipes_state_a_reason():
    current = ledger.load()
    empty = [rid for rid, reason in current.untestable.items() if not reason.strip()]
    assert not empty, f"untestable without a reason is just untested: {empty}"


def test_the_pending_list_only_ever_shrinks():
    pending = len(ledger.load().pending)
    assert pending <= MAX_PENDING, (
        f"{pending} recipes pending, ceiling is {MAX_PENDING}. A new claim was added "
        "without a test. Add the test, or lower nothing and reconsider the claim."
    )


def test_no_recipe_is_recorded_as_failing():
    """A failing recipe is a claim the documentation still makes and shouldn't."""
    failing = {rid: entry["test"]
               for rid, entry in ledger.load().recipes.items()
               if entry["status"] == "fail"}
    assert not failing, (
        f"the playbook claims these and the live suite disproves them: {failing}"
    )
```

- [ ] **Step 2: Run it**

Run: `python3 -m pytest tests/test_coverage_invariant.py -v`

Expected: all eight pass against the ledger written in Task 4.

- [ ] **Step 3: Prove the gate actually catches something**

Temporarily add a row to `docs/PLAYBOOK.md` under `## Tag`:

```markdown
| **Fabricate** | `AS: this does not exist` |
```

Run: `python3 -m pytest tests/test_coverage_invariant.py -v`

Expected: `test_every_recipe_is_accounted_for` fails naming `tag.fabricate`. Remove the row and re-run to confirm it passes again. A gate that has never been seen failing is not known to work.

- [ ] **Step 4: Commit**

```bash
git add tests/test_coverage_invariant.py
git commit -m "Fail the build when a claim has no test behind it"
```

---

### Task 6: Generate the capability matrix from the ledger

**Files:**
- Create: `things3/verification/render.py`
- Create: `tests/test_render.py`
- Modify: `README.md` (wrap the matrix in generated markers)
- Modify: `tests/test_coverage_invariant.py` (assert the committed block matches the ledger)

**Interfaces:**
- Consumes: `things3.verification.ledger.load`
- Produces:
  - `things3.verification.render.matrix(ledger: Ledger) -> str` — the markdown table
  - `things3.verification.render.apply(text: str, block: str, name: str) -> str` — replace one marked block
  - `things3.verification.render.CellConflictError` — two recipes grade the same cell differently
  - `things3.verification.render.ROWS`, `COLUMNS` — the fixed axes

- [ ] **Step 1: Write the failing test**

Create `tests/test_render.py`:

```python
"""The matrix is generated, so a claim cannot outlive the test behind it."""
import pytest

from things3.verification import ledger, render


def _ledger(cells: dict[str, str]) -> ledger.Ledger:
    """A ledger whose only content is cell -> grade, one recipe per cell."""
    return ledger.Ledger(recipes={
        f"r{n}": {"status": "pass", "test": "t", "cell": cell, "grade": grade,
                  "first_verified": "2026-08-07", "last_verified": "2026-08-07"}
        for n, (cell, grade) in enumerate(cells.items())
    })


def test_a_graded_cell_appears_in_the_table():
    table = render.matrix(_ledger({"todo/D": "✅"}))
    row = next(line for line in table.splitlines() if "To-do" in line)
    assert "✅" in row


def test_an_ungraded_cell_renders_as_untested():
    table = render.matrix(ledger.Ledger())
    assert "·" in table, "cells with no passing test must be visibly untested"


def test_two_recipes_grading_one_cell_differently_is_an_error():
    conflicting = _ledger({"todo/D": "✅"})
    conflicting.recipes["other"] = {"status": "pass", "test": "t2",
                                    "cell": "todo/D", "grade": "🟡",
                                    "first_verified": None, "last_verified": "x"}
    with pytest.raises(render.CellConflictError, match="todo/D"):
        render.matrix(conflicting)


def test_a_failing_recipe_does_not_grade_its_cell():
    failed = _ledger({"todo/D": "✅"})
    failed.recipes["r0"]["status"] = "fail"
    table = render.matrix(failed)
    row = next(line for line in table.splitlines() if "To-do" in line)
    assert "✅" not in row


def test_apply_replaces_only_the_marked_block():
    text = ("before\n<!-- generated:matrix -->\nold\n<!-- /generated:matrix -->\nafter\n")
    result = render.apply(text, "new", "matrix")
    assert "old" not in result
    assert result.startswith("before") and result.rstrip().endswith("after")


def test_apply_refuses_when_the_markers_are_missing():
    with pytest.raises(ValueError, match="matrix"):
        render.apply("no markers here", "new", "matrix")
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python3 -m pytest tests/test_render.py -v`

Expected: `ImportError: cannot import name 'render'`.

- [ ] **Step 3: Write the renderer**

Create `things3/verification/render.py`:

```python
"""Generate the capability matrix from the ledger.

Hand-written, the matrix could claim something no test supports -- which is how
this project ended up with 78 documented recipes and seven tests. Generated, a
cell can only carry a grade that a passing test put there.
"""
from __future__ import annotations

import re

from .ledger import Ledger

ROWS = [("todo", "To-do"), ("project", "Project"), ("area", "Area"),
        ("tag", "Tag"), ("heading", "Heading"),
        ("checklist", "Checklist item"), ("recurrence", "Recurrence")]

COLUMNS = ["C", "R", "U", "D", "Dup", "Move", "Done", "Rest"]

#: Cells the platform has no concept of -- not gaps, just inapplicable.
NOT_APPLICABLE = {
    "area/Move", "area/Done", "tag/Done", "heading/Rest", "checklist/Rest",
    "recurrence/Dup", "recurrence/Move", "recurrence/Done", "recurrence/Rest",
}

UNTESTED = "·"


class CellConflictError(ValueError):
    """Two passing recipes grade the same cell differently."""


def _grades(ledger: Ledger) -> dict[str, str]:
    grades: dict[str, tuple[str, str]] = {}
    for recipe_id, entry in ledger.recipes.items():
        cell, grade = entry.get("cell"), entry.get("grade")
        if not cell or not grade or entry["status"] != "pass":
            continue
        if cell in grades and grades[cell][0] != grade:
            raise CellConflictError(
                f"{cell} is graded {grades[cell][0]} by {grades[cell][1]} and "
                f"{grade} by {recipe_id}; one of them is wrong"
            )
        grades[cell] = (grade, recipe_id)
    return {cell: grade for cell, (grade, _) in grades.items()}


def matrix(ledger: Ledger) -> str:
    grades = _grades(ledger)
    lines = ["| | " + " | ".join(COLUMNS) + " |",
             "|---|" + ":-:|" * len(COLUMNS)]
    for slug, label in ROWS:
        cells = []
        for column in COLUMNS:
            key = f"{slug}/{column}"
            if key in NOT_APPLICABLE:
                cells.append("➖")
            else:
                cells.append(grades.get(key, UNTESTED))
        lines.append(f"| **{label}** | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def apply(text: str, block: str, name: str) -> str:
    """Replace the content between <!-- generated:name --> markers."""
    pattern = re.compile(
        rf"(<!-- generated:{name} -->\n).*?(\n<!-- /generated:{name} -->)",
        re.DOTALL,
    )
    if not pattern.search(text):
        raise ValueError(f"no <!-- generated:{name} --> block found")
    return pattern.sub(lambda m: m.group(1) + block + m.group(2), text)
```

- [ ] **Step 4: Carry `cell` and `grade` into the ledger**

The marker already accepts them; `merge` must store them. In `things3/verification/ledger.py`, extend the entry built inside `merge`:

```python
        recipes[recipe_id] = {
            "status": result["status"],
            "test": result["test"],
            "cell": result.get("cell") or previous.get("cell"),
            "grade": result.get("grade") or previous.get("grade"),
            "first_verified": first,
            "last_verified": today,
        }
```

and in `tests/live/conftest.py`, capture them from the marker:

```python
    _RESULTS[marker.args[0]] = {
        "status": status,
        "test": item.nodeid,
        "cell": marker.kwargs.get("cell"),
        "grade": marker.kwargs.get("grade"),
    }
```

- [ ] **Step 5: Run the renderer tests**

Run: `python3 -m pytest tests/test_render.py tests/test_ledger.py -v`

Expected: all pass.

- [ ] **Step 6: Wrap the README matrix in markers**

In `README.md`, replace the matrix table (the block starting `| | C | R | U | D |`) with:

```markdown
<!-- generated:matrix -->
<!-- /generated:matrix -->
```

leaving the **Columns** and **Cells** legend paragraphs below it untouched — those are prose and stay hand-written. Add `·` to the legend:

```markdown
**Cells** — ✅ works directly · 🟡 cheap validated workaround · 🔶 expensive workaround (rebuild the
parent, or restore from a backup) · ⚠️ works but **irreversible** · ❌ impossible by any route,
including composition · ➖ not applicable · `·` no live test yet
```

- [ ] **Step 7: Generate it**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
from things3.verification import ledger, render

readme = Path("README.md")
readme.write_text(
    render.apply(readme.read_text(encoding="utf-8"),
                 render.matrix(ledger.load()), "matrix"),
    encoding="utf-8",
)
print(render.matrix(ledger.load()))
PY
```

Expected: a table where the eight verified cells carry their grade and the rest show `·`. This is the honest current state, and it is meant to look sparse: the second plan fills it in.

- [ ] **Step 8: Guard the generated block against hand edits**

Append to `tests/test_coverage_invariant.py`:

```python
def test_the_readme_matrix_matches_the_ledger():
    """Hand-editing a generated block would reintroduce untested claims."""
    from things3.verification import render

    readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    expected = render.matrix(ledger.load())
    assert expected in readme, (
        "the matrix in README.md is out of date; regenerate it from VERIFIED.json"
    )
```

- [ ] **Step 9: Run the full mocked suite**

Run: `python3 -m pytest -v`

Expected: all pass, including the new guard.

- [ ] **Step 10: Commit**

```bash
git add things3/verification/render.py things3/verification/ledger.py \
        tests/test_render.py tests/test_coverage_invariant.py \
        tests/live/conftest.py README.md VERIFIED.json
git commit -m "Generate the capability matrix from the ledger"
```

---

### Task 7: Corrections and documentation

**Files:**
- Modify: `pyproject.toml`, `things3/__init__.py` (version alignment)
- Modify: `things3/doctor.py` (language check)
- Modify: `docs/PLAYBOOK.md` (delete recipe, list-id recipes)
- Modify: `CONTRIBUTING.md`, `README.md`, `CHANGELOG.md`
- Modify: `.github/workflows/tests.yml`

**Interfaces:**
- Consumes: `things3.lists`
- Produces: `things3.doctor._trash_reachable() -> Check`

- [ ] **Step 1: Align the version**

`pyproject.toml` and `things3/__init__.py` both say `0.2.0` while `CHANGELOG.md` documents `0.3.0`. Set both to `0.3.0`.

- [ ] **Step 2: Write the failing doctor test**

Append to `tests/test_cli.py`:

```python
def test_trash_check_reports_the_localized_name(monkeypatch):
    """Resolving the Trash by id is what makes this work in any language."""
    from things3 import doctor

    monkeypatch.setattr(doctor.applescript, "run", lambda script: type(
        "R", (), {"ok": True, "stdout": "Papierkorb", "stderr": ""})())
    check = doctor._trash_reachable()
    assert check.ok
    assert "Papierkorb" in check.detail


def test_trash_check_fails_when_the_list_cannot_be_resolved(monkeypatch):
    from things3 import doctor

    monkeypatch.setattr(doctor.applescript, "run", lambda script: type(
        "R", (), {"ok": False, "stdout": "", "stderr": "-1728"})())
    check = doctor._trash_reachable()
    assert not check.ok
    assert check.fix
```

- [ ] **Step 3: Run it to make sure it fails**

Run: `python3 -m pytest tests/test_cli.py -k trash -v`

Expected: `AttributeError: module 'things3.doctor' has no attribute '_trash_reachable'`.

- [ ] **Step 4: Add the check**

In `things3/doctor.py`, import `lists` alongside the existing imports and add:

```python
def _trash_reachable() -> Check:
    """Resolve the Trash by id, and report the name the user actually sees.

    Reporting the localized name is deliberate: it tells someone reading the
    output in German that the library found the right list without depending on
    what it is called.
    """
    result = applescript.run(f"  return name of {lists.specifier(lists.TRASH)}")
    if not result.ok:
        return Check(
            "Trash reachable", False, result.stderr.strip()[:80],
            fix="Things could not resolve its own Trash list. Restart the app; if it "
                "persists, open an issue with your Things version.",
        )
    return Check("Trash reachable", True, f'shown as "{result.stdout.strip()}"')
```

and add `_trash_reachable` to the list of checks the `doctor` command runs, after the automation-permission check.

- [ ] **Step 5: Run the tests and the command**

Run: `python3 -m pytest tests/test_cli.py -v && python3 -m things3.cli doctor`

Expected: tests pass, and `doctor` prints `[  ok] Trash reachable: shown as "Trash"`.

- [ ] **Step 6: Correct the playbook**

Three edits in `docs/PLAYBOOK.md`, all replacing a name-addressed or superseded recipe. Keep the action text identical, because the recipe id derives from it and changing it would orphan the ledger entry.

| Line | From | To |
|---|---|---|
| 28 | `list "Today"` | `list id "TMTodayListSource"` |
| 29 | `list "Today"` | `list id "TMTodayListSource"` |
| 39 | `AS: delete (to do id "<uuid>")` — goes to the **native Trash**, reversible | ``AS: move (to do id "<uuid>") to list id "TMTrashListSource"`` — goes to the **native Trash**, reversible. `delete` also targets the Trash but fails intermittently with `-1728`; this route has not |
| 40 | `list "Anytime"` | `list id "TMNextListSource"` |
| 42 | `list "Today"` | `list id "TMTodayListSource"` |
| 63 | `list "Anytime"` | `list id "TMNextListSource"` |

Add a row to the Notation table:

```markdown
| `list id "…"` | Built-in lists are addressed by **id**, never by name: names are localized and Things ships nine languages |
```

Then confirm the ids did not change:

Run: `python3 -m pytest tests/test_recipes.py tests/test_coverage_invariant.py -v`

Expected: all pass. A failure here means an action label was edited by accident.

- [ ] **Step 7: Update the guidance documents**

`CONTRIBUTING.md` — replace the "Running the tests" block:

```markdown
## Running the tests

```bash
pytest                         # mocked suite; no Things needed, runs in CI
pytest -m 'live and not i18n'  # talks to a real Things 3 install; opt-in
pytest -m i18n                 # also restarts Things and changes its language; opt-in
```

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
```

`README.md` — extend the "Verified limits" table with a row:

```markdown
| Language | Built-in lists are addressed by stable id, not by localized name, so the library does not depend on the language Things runs in. Proven by `pytest -m i18n`, which switches the app's language and asserts both routes |
```

`CHANGELOG.md` — add under `## [0.3.0]`:

```markdown
### Added
- `VERIFIED.json`: a committed record of which playbook recipes were reproduced live, when they
  were first verified, and against which Things and macOS versions. The capability matrix in the
  README is generated from it, so a claim cannot outlive the test behind it.
- Coverage invariant in the mocked suite: a recipe without a test, a test claiming a recipe that
  does not exist, or a matrix out of step with the ledger all fail the build.
- `things3/lists.py`, and an i18n suite that switches the language Things runs in to prove the
  library does not depend on it.

### Fixed
- Built-in lists were addressed by display name, which is localized. Every delete would have
  failed for users running Things in any of its eight other languages.
```

If Task 1 showed that names are *not* localized, this entry belongs under `### Changed` and must say the by-id route removes a dependency on display names rather than fixing a failure — do not describe a bug that was not reproduced.

- [ ] **Step 8: Add the invariant to CI**

In `.github/workflows/tests.yml`, the unit job already runs `pytest`, which now includes the invariant. Extend the `live-collects` job's collection command so the i18n module is collected too but never executed:

```yaml
      - run: pytest -m 'live or i18n' --collect-only -q
```

- [ ] **Step 9: Run everything**

Run:

```bash
python3 -m pytest -v && python3 -m pytest -m 'live and not i18n' -v
```

Expected: mocked suite green, live suite green, nothing left behind, `VERIFIED.json` unchanged apart from `last_verified`.

- [ ] **Step 10: Commit and open the PR**

```bash
git add -u && git add VERIFIED.json
git commit -m "Align the version, teach doctor about the Trash, and correct the playbook"
git push -u origin validation-ledger
gh pr create --title "Validation ledger and language portability" --body "$(cat <<'EOF'
Makes the project's own rule enforceable: a capability claim needs a live test.

- recipe ids derived from the playbook, so there is no second registry to drift
- `VERIFIED.json` records what was reproduced, when, and against which versions
- a meta-test in the mocked suite fails the build when a claim has no test
- the capability matrix is generated from the ledger
- built-in lists are addressed by stable id rather than localized name

The matrix is deliberately sparse: it now shows only what a passing test supports.
A second plan fills in the remaining recipes.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage.** Every section maps to a task: unit of validation → Task 3; ledger → Task 4; coverage invariant → Task 5; generated documentation → Task 6; language portability → Tasks 1 and 2; test isolation → Task 4 Step 6; corrections → Task 7. Two deviations from the spec, both deliberate:

1. The spec described a custom `@verifies(...)` decorator. The plan uses `@pytest.mark.verifies(...)` — same behaviour, no machinery, and it keeps pytest out of the library's imports.
2. The spec described the playbook carrying explicit recipe ids. The plan derives them from the action text instead, which was validated against the real document (78 ids, all unique) and removes the possibility of the two drifting.

One addition the spec did not anticipate: the `pending` list and `MAX_PENDING` ceiling, needed because the invariant has to land before coverage is complete or it could never be introduced at all.

**Ordering.** Task 1 comes first and deliberately may disprove the premise of Task 2. That is the correct order: the alternative is changing code to fix a defect that was never observed.

**Out of scope, as agreed.** The remaining 67 recipes (second plan), the MCP server, and older Things versions.
