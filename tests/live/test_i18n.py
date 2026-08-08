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
