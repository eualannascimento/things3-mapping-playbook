"""Reproduce the application-level recipes that are safe to run unattended.

`app.empty-the-trash`, `app.archive-completed` and `app.quick-entry-panel` are
recorded `untestable` in the ledger instead: each is global, irreversible, or
takes over the screen, so no test here calls them.
"""
from __future__ import annotations

import pytest

from things3 import applescript

pytestmark = pytest.mark.live


@pytest.mark.verifies("app.built-in-lists")
def test_built_in_lists_are_nine_not_seven(sandbox):
    result = applescript.run("  return name of every list")
    assert result.ok
    names = [n.strip() for n in result.stdout.split(",")]
    for expected in ("Inbox", "Today", "Anytime", "Someday", "Logbook", "Trash"):
        assert expected in names
    assert "Tomorrow" in names, "undocumented but present"
    assert "Later Projects" in names, "undocumented but present"


@pytest.mark.verifies("app.current-list")
def test_current_list_returns_a_name(sandbox):
    result = applescript.run("  return current list name")
    assert result.ok
    assert result.stdout.strip()


@pytest.mark.verifies("app.ui-selection")
def test_ui_selection_returns_a_list_without_erroring(sandbox):
    """No item is selected in an automated run; the claim is that the query works."""
    result = applescript.run("  return name of every selected to do")
    assert result.ok
