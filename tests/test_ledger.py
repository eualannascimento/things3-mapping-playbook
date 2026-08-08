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
