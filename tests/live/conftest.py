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

from things3 import applescript, ops, read, urlscheme

PREFIX = "zzlive-"


def pytest_configure(config):
    config.addinivalue_line("markers", "live: talks to a real Things 3 install")


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

    Headings are the one thing that cannot be deleted by any route -- they go
    away with their project, so they are not counted as leftovers.
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
                f'  try\n    move ({spec} id "{uuid}") to list "Trash"\n  end try'
            )

        areas = conn.execute(
            "SELECT title FROM TMArea WHERE title LIKE ?", (f"{PREFIX}%",)
        ).fetchall()
        for (title,) in areas:
            applescript.run(f'  try\n    delete area "{applescript.escape(title)}"\n  end try')

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
            """
            urlscheme.create_project_with_headings(
                f"{PREFIX}{project_title}", [f"{PREFIX}{heading_title}"]
            )
            self.settle(2.5)
            row = conn.execute(
                "SELECT uuid, project FROM TMTask WHERE title = ? AND type = 2",
                (f"{PREFIX}{heading_title}",),
            ).fetchone()
            assert row is not None, "heading creation via the project payload failed"
            created.append(("project", row[1]))
            return row[1], row[0]

        def area(self, title: str = "area") -> str:
            name = f"{PREFIX}{title}"
            ops.create(ops.Kind.AREA, name)
            created.append(("area", name))
            return name

        def settle(self, seconds: float = 1.5) -> None:
            """Give Things time to persist before reading SQLite back."""
            time.sleep(seconds)

    yield Sandbox()

    time.sleep(1)
    for kind, identifier in reversed(created):
        if kind == "area":
            applescript.run(
                f'  try\n    delete area "{applescript.escape(identifier)}"\n  end try'
            )
        else:
            applescript.run(
                f'  try\n    move ({kind} id "{identifier}") to list "Trash"\n  end try'
            )
