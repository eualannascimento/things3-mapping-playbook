import json
import urllib.parse

import pytest

from things3 import applescript, urlscheme


# --- AppleScript -----------------------------------------------------------

def test_escape_neutralises_quotes_and_backslashes():
    assert applescript.escape('say "hi"\\now') == 'say \\"hi\\"\\\\now'


def test_batch_isolates_each_statement_in_its_own_try():
    script = None

    def fake_run(body, **kwargs):
        nonlocal script
        script = body
        return applescript.Result(0, "", "")

    original, applescript.run = applescript.run, fake_run
    try:
        applescript.run_batch([("a", 'set x to 1'), ("b", 'set y to 2')])
    finally:
        applescript.run = original

    assert script.count("on error") == 2, "each statement needs its own try/on error"
    assert "set x to 1" in script and "set y to 2" in script


def test_batch_reports_failures_per_item():
    original = applescript.run
    applescript.run = lambda body, **kw: applescript.Result(0, "b=boom", "")
    try:
        errors = applescript.run_batch([("a", "ok"), ("b", "bad")])
    finally:
        applescript.run = original
    assert errors == {"b": "boom"}


def test_batch_marks_whole_chunk_failed_when_script_does_not_run():
    original = applescript.run
    applescript.run = lambda body, **kw: applescript.Result(1, "", "syntax error")
    try:
        errors = applescript.run_batch([("a", "x"), ("b", "y")])
    finally:
        applescript.run = original
    assert set(errors) == {"a", "b"}


@pytest.mark.parametrize("stderr,expected", [
    ("execution error: Connection is invalid. (-609)", True),
    ("Application isn't running. (-600)", True),
    ("Apple event timed out. (-1712)", True),
    ("Can't get to do id. (-1728)", False),
    ("syntax error", False),
])
def test_transient_error_classification(stderr, expected):
    """Retrying a permanent error just delays the failure."""
    assert applescript.Result(1, "", stderr).is_transient is expected


def test_oversized_batches_are_chunked():
    huge = [(str(i), "x" * 50_000) for i in range(5)]
    chunks = applescript._chunks(huge)
    assert len(chunks) > 1
    assert sum(len(c) for c in chunks) == 5


# --- URL scheme ------------------------------------------------------------

def test_url_is_built_without_token_by_default():
    url = urlscheme.build_url([{"type": "to-do", "attributes": {"title": "x"}}])
    assert url.startswith("things:///json?data=")
    assert "auth-token" not in url


def test_url_preserves_accents_through_encoding():
    payload = [{"type": "to-do", "attributes": {"title": "Café à noite"}}]
    url = urlscheme.build_url(payload)
    decoded = json.loads(urllib.parse.unquote(url.split("data=")[1]))
    assert decoded[0]["attributes"]["title"] == "Café à noite"


def test_open_command_keeps_things_in_the_background():
    """Without -g -j, a closed Things steals the user's focus."""
    assert urlscheme.OPEN_COMMAND == ["open", "-g", "-j"]


def test_checklist_payload_always_sends_completed_flag():
    payload = urlscheme.checklist_payload([{"title": "a"}, {"title": "b", "completed": True}])
    assert payload[0]["attributes"]["completed"] is False
    assert payload[1]["attributes"]["completed"] is True


def test_replace_checklist_refuses_above_platform_limit():
    items = [{"title": f"i{n}"} for n in range(urlscheme.MAX_CHECKLIST_ITEMS + 1)]
    with pytest.raises(ValueError, match="Refusing rather than silently truncating"):
        urlscheme.replace_checklist("uuid", items)


def test_missing_token_error_explains_how_to_get_one(monkeypatch):
    monkeypatch.delenv("THINGS_AUTH_TOKEN", raising=False)
    with pytest.raises(urlscheme.MissingTokenError, match="Enable Things URLs"):
        urlscheme.auth_token()


def test_token_is_read_only_from_environment(monkeypatch):
    monkeypatch.setenv("THINGS_AUTH_TOKEN", "secret")
    assert urlscheme.auth_token() == "secret"
