"""Fixtures for the live suite, which talks to a real Things install.

Three rules keep this safe to run against someone's actual database:

1. Every object created here carries a prefix, is tracked, and is torn down.
2. Nothing touches an object it did not create -- with one deliberate exception,
   the recurrence guard, which only *reads* a real repeating task.
3. Teardown is checked, not hoped for. A session-level sweep fails the run if
   anything prefixed survives, because a test suite that litters someone's task
   list is worse than no test suite.
"""
from __future__ import annotations

import platform
import time

import pytest

from things3 import applescript, lists, ops, read, urlscheme

PREFIX = "zzlive-"


def pytest_configure(config):
    config.addinivalue_line("markers", "live: talks to a real Things 3 install")
    config.addinivalue_line(
        "markers",
        "verifies(recipe, cell=None, grade=None): the playbook recipe this test reproduces",
    )


@pytest.fixture(scope="session", autouse=True)
def require_things():
    if platform.system() != "Darwin":
        pytest.skip("live suite needs macOS")
    probe = applescript.run("  return name")
    if not probe.ok:
        pytest.skip(f"Things 3 not reachable: {probe.stderr.strip()[:80]}")


@pytest.fixture(scope="session", autouse=True)
def sweep_after_session(require_things):
    """Last line of defence: nothing prefixed may outlive the session.

    Headings are not counted as leftovers here, but they are not actually
    gone: sending the parent project to the Trash does not set trashed=1 on
    its heading rows. They become unreachable through the app -- their parent
    is gone -- but the row persists in SQLite, addressable by uuid, until the
    Trash is emptied. Confirmed live: `delete` and moving to the Trash both
    still fail on a heading even after its project is trashed. Only actually
    emptying the Trash was observed to clear them, and this project never
    calls that from automation (see `app.empty-the-trash` in the ledger) --
    so a live suite that exercises headings leaves inert, invisible residue
    behind on every run. Run `pytest -m live` sparingly, or empty the Trash
    by hand occasionally if this bothers you.
    """
    yield
    time.sleep(2)
    conn = read.connect()
    try:
        leftovers = conn.execute(
            "SELECT uuid, title, type FROM TMTask "
            "WHERE title LIKE ? AND trashed = 0 AND type IN (0, 1)",
            (f"{PREFIX}%",),
        ).fetchall()
        for uuid, _title, kind in leftovers:
            spec = "project" if kind == 1 else "to do"
            applescript.run(
                f'  try\n    move ({spec} id "{uuid}") to {lists.specifier(lists.TRASH)}\n  end try'
            )

        areas = conn.execute(
            "SELECT title FROM TMArea WHERE title LIKE ?", (f"{PREFIX}%",)
        ).fetchall()
        for (title,) in areas:
            applescript.run(f'  try\n    delete area "{applescript.escape(title)}"\n  end try')

        tags = conn.execute(
            "SELECT title FROM TMTag WHERE title LIKE ?", (f"{PREFIX}%",)
        ).fetchall()
        for (title,) in tags:
            applescript.run(f'  try\n    delete tag "{applescript.escape(title)}"\n  end try')

        time.sleep(2)
        remaining = conn.execute(
            "SELECT title FROM TMTask WHERE title LIKE ? AND trashed = 0 AND type IN (0, 1)",
            (f"{PREFIX}%",),
        ).fetchall()
        assert not remaining, (
            f"live suite left {len(remaining)} object(s) behind: "
            f"{[r[0] for r in remaining]}"
        )
    finally:
        conn.close()


@pytest.fixture
def conn():
    connection = read.connect()
    yield connection
    connection.close()


@pytest.fixture
def sandbox(conn):
    """Create disposable objects and guarantee they are cleaned up."""
    created: list[tuple[str, str]] = []  # (applescript specifier kind, uuid)

    class Sandbox:
        def todo(self, title: str = "task") -> str:
            uuid = ops.create(ops.Kind.TODO, f"{PREFIX}{title}").detail
            created.append(("to do", uuid))
            return uuid

        def project(self, title: str = "project") -> str:
            uuid = ops.create(ops.Kind.PROJECT, f"{PREFIX}{title}").detail
            created.append(("project", uuid))
            return uuid

        def project_with_heading(self, project_title: str,
                                 heading_title: str) -> tuple[str, str]:
            """Create a project carrying a heading -- the only way headings exist.

            Returns (project_uuid, heading_uuid). Tracked like anything else, so
            it cannot leak the way a directly-built payload would.

            A heading never receives trashed=1 when its parent project is sent
            to the Trash -- confirmed live, and the reason headings must be
            looked up scoped to *this* project's own uuid, not by title alone.
            A stale heading from an earlier run, invisible in the app but still
            present in SQLite, would otherwise be a silent false match.
            """
            urlscheme.create_project_with_headings(
                f"{PREFIX}{project_title}", [f"{PREFIX}{heading_title}"]
            )
            self.settle(2.5)
            project_row = conn.execute(
                "SELECT uuid FROM TMTask WHERE title = ? AND type = 1 AND trashed = 0 "
                "ORDER BY creationDate DESC LIMIT 1",
                (f"{PREFIX}{project_title}",),
            ).fetchone()
            assert project_row is not None, "project creation via the headings payload failed"
            project_uuid = project_row[0]

            heading_row = conn.execute(
                "SELECT uuid FROM TMTask WHERE project = ? AND type = 2 AND title = ?",
                (project_uuid, f"{PREFIX}{heading_title}"),
            ).fetchone()
            assert heading_row is not None, "heading creation via the project payload failed"
            created.append(("project", project_uuid))
            return project_uuid, heading_row[0]

        def area(self, title: str = "area") -> str:
            name = f"{PREFIX}{title}"
            ops.create(ops.Kind.AREA, name)
            created.append(("area", name))
            return name

        def tag(self, title: str = "tag") -> str:
            name = f"{PREFIX}{title}"
            ops.create(ops.Kind.TAG, name)
            created.append(("tag", name))
            return name

        def settle(self, seconds: float = 1.5) -> None:
            """Give Things time to persist before reading SQLite back."""
            time.sleep(seconds)

        def track(self, kind: str, identifier: str) -> None:
            """Register an object this fixture did not itself create.

            For recipes that build an object through a route none of the helpers
            above wrap directly (natural-language parsing, for instance) -- so
            teardown still reaches it.
            """
            created.append((kind, identifier))

    yield Sandbox()

    time.sleep(1)
    for kind, identifier in reversed(created):
        if kind == "area":
            applescript.run(
                f'  try\n    delete area "{applescript.escape(identifier)}"\n  end try'
            )
        elif kind == "tag":
            applescript.run(
                f'  try\n    delete tag "{applescript.escape(identifier)}"\n  end try'
            )
        else:
            applescript.run(
                f'  try\n    move ({kind} id "{identifier}") to {lists.specifier(lists.TRASH)}\n  end try'
            )


# --- ledger: record which claims were reproduced, not just that they ran -----

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
    _RESULTS[marker.args[0]] = {
        "status": status,
        "test": item.nodeid,
        "cell": marker.kwargs.get("cell"),
        "grade": marker.kwargs.get("grade"),
    }


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
