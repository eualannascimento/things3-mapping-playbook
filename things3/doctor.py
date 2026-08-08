"""Diagnose the environment before anything else fails confusingly.

Most "it doesn't work" reports come down to one of a handful of causes, and each
produces an error far from its root: automation permission not granted looks like
a missing object; Things never launched looks like a missing database; a missing
token looks like an update that silently did nothing.

Every check reports what to do about it, not just that it failed.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass

from . import applescript, lists, read

THINGS_APP = "/Applications/Things3.app"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""
    required: bool = True

    @property
    def symbol(self) -> str:
        if self.ok:
            return "ok"
        return "FAIL" if self.required else "warn"


def _python_version() -> Check:
    major, minor = sys.version_info[:2]
    ok = (major, minor) >= (3, 10)
    return Check(
        "Python >= 3.10", ok, f"running {major}.{minor}",
        fix="" if ok else "Install a newer Python; this package uses 3.10+ syntax.",
    )


def _macos() -> Check:
    ok = platform.system() == "Darwin"
    return Check(
        "macOS", ok, platform.platform() if ok else f"running {platform.system()}",
        fix="" if ok else "AppleScript is macOS-only. There is no route on other systems.",
    )


def _things_installed() -> Check:
    ok = os.path.isdir(THINGS_APP)
    version = ""
    if ok:
        try:
            version = subprocess.run(
                ["/usr/libexec/PlistBuddy", "-c", "Print :CFBundleShortVersionString",
                 f"{THINGS_APP}/Contents/Info.plist"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            version = "unknown"
    return Check(
        "Things 3 installed", ok, f"version {version}" if ok else "not found in /Applications",
        fix="" if ok else "Install Things 3 from the Mac App Store or culturedcode.com.",
    )


def _database() -> Check:
    try:
        path = read.find_database()
    except FileNotFoundError as exc:
        return Check("Database found", False, str(exc).splitlines()[0],
                     fix="Open Things 3 at least once so it creates its database.")
    return Check("Database found", True, str(path.parent.parent.name))


def _database_readable() -> Check:
    try:
        conn = read.connect()
    except Exception as exc:  # sqlite errors vary by cause
        return Check("Database readable", False, str(exc),
                     fix="Grant Full Disk Access to your terminal in System Settings -> "
                         "Privacy & Security, so it can read the app's container.")
    try:
        count = conn.execute("SELECT COUNT(*) FROM TMTask").fetchone()[0]
        return Check("Database readable", True, f"{count} rows in TMTask")
    except Exception as exc:
        return Check("Database readable", False, f"schema unexpected: {exc}",
                     fix="The Things schema may have changed in a recent update. "
                         "Open an issue with your Things version.")
    finally:
        conn.close()


def _automation_permission() -> Check:
    """The most common silent failure: the permission prompt was never answered."""
    if platform.system() != "Darwin":
        return Check("AppleScript permission", False, "not applicable off macOS")
    proc = subprocess.run(
        ["osascript", "-e", 'tell application "Things3" to return name'],
        capture_output=True, text=True,
    )
    if proc.returncode == 0:
        return Check("AppleScript permission", True, "granted")
    denied = "-1743" in proc.stderr or "not allowed" in proc.stderr.lower()
    return Check(
        "AppleScript permission", False,
        "denied" if denied else proc.stderr.strip()[:80],
        fix="System Settings -> Privacy & Security -> Automation: allow your terminal "
            "to control Things3. If the prompt never appeared, run any AppleScript "
            "command from the terminal to trigger it.",
    )


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


def _auth_token() -> Check:
    """Optional: only `operation: update` needs it (editing existing checklists)."""
    present = bool(os.environ.get("THINGS_AUTH_TOKEN"))
    return Check(
        "THINGS_AUTH_TOKEN", present,
        "set" if present else "not set (only needed to edit existing checklist items)",
        fix="" if present else
            "Things -> Settings -> General -> Enable Things URLs -> Manage, then "
            "export THINGS_AUTH_TOKEN in your shell profile. Note it must be in a "
            "file your non-interactive shell reads (~/.zshenv, not just ~/.zshrc).",
        required=False,
    )


def _open_command() -> Check:
    ok = shutil.which("open") is not None
    return Check(
        "`open` available", ok,
        "found" if ok else "missing",
        fix="" if ok else "The URL scheme backend shells out to `open`; it ships with macOS.",
    )


def run_all() -> list[Check]:
    checks = [_python_version(), _macos()]
    if checks[-1].ok:
        checks += [_things_installed(), _database(), _database_readable(),
                   _automation_permission(), _trash_reachable(),
                   _open_command(), _auth_token()]
    return checks


def summarise(checks: list[Check]) -> tuple[bool, str]:
    """Return (healthy, human-readable report)."""
    lines = []
    for check in checks:
        lines.append(f"  [{check.symbol:>4}] {check.name}: {check.detail}")
        if not check.ok and check.fix:
            for wrapped in _wrap(check.fix, 68):
                lines.append(f"         {wrapped}")
    blocking = [c for c in checks if not c.ok and c.required]
    if blocking:
        lines.append("")
        lines.append(f"  {len(blocking)} blocking problem(s). Fix those first.")
    else:
        lines.append("")
        lines.append("  Ready.")
    return not blocking, "\n".join(lines)


def _wrap(text: str, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines
