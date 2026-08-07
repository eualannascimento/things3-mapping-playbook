"""AppleScript backend: the default path for writes.

Chosen as the default because it needs no credential and never steals focus.
It cannot see checklist items or headings as classes -- but a heading object is
still addressable as `to do id "<uuid>"`, which is the only way to rename one.
"""
from __future__ import annotations

import platform
import subprocess
import time
from dataclasses import dataclass

# Apple Event errors worth retrying: the app was busy or still launching.
# Without a retry these were silently reported as real failures.
TRANSIENT_ERRORS = ("-609", "-600", "-1712")

# One `osascript` spawn costs ~0.16s, so one call per fix made cost grow
# linearly (200 fixes ≈ 33s). Batching keeps it at one spawn.
_BATCH_DELIMITER = "|||"
_MAX_BATCH_CHARS = 120_000


class AppleScriptError(RuntimeError):
    pass


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def is_transient(self) -> bool:
        return any(code in self.stderr for code in TRANSIENT_ERRORS)


def escape(value: str) -> str:
    """Escape a string for use as an AppleScript literal.

    Never interpolate user text into a script without this: it breaks the script
    and, with adversarial input, allows AppleScript injection.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def run(body: str, *, retries: int = 2, delay_seconds: float = 1.0) -> Result:
    """Run a script body inside `tell application "Things3"`.

    Retries transient Apple Event errors with backoff; permanent errors (missing
    object, syntax) fail immediately.
    """
    if platform.system() != "Darwin":
        raise AppleScriptError("AppleScript only runs on macOS")

    script = f'tell application "Things3"\n{body}\nend tell'
    result = _once(script)
    attempt = 0
    while not result.ok and result.is_transient and attempt < retries:
        attempt += 1
        time.sleep(delay_seconds * attempt)
        result = _once(script)
    return result


def _once(script: str) -> Result:
    proc = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True
    )
    return Result(proc.returncode, proc.stdout, proc.stderr)


def run_batch(statements: list[tuple[str, str]]) -> dict[str, str]:
    """Run many statements in a single spawn, isolating failures per item.

    `statements` is a list of (key, applescript_line). Each line runs inside its
    own `try`, so one failure does not take down the rest of the batch.

    Returns {key: error_message} for the ones that failed -- empty means all
    succeeded.
    """
    errors: dict[str, str] = {}
    for chunk in _chunks(statements):
        lines = ["  set failures to {}"]
        for key, statement in chunk:
            safe_key = escape(key)
            lines += [
                "  try",
                f"    {statement}",
                "  on error errMsg",
                f'    set end of failures to "{safe_key}=" & errMsg',
                "  end try",
            ]
        lines += [
            f'  set AppleScript\'s text item delimiters to "{_BATCH_DELIMITER}"',
            "  return failures as string",
        ]
        result = run("\n".join(lines))
        if not result.ok:
            for key, _ in chunk:
                errors[key] = result.stderr.strip()
            continue
        for entry in filter(None, result.stdout.strip().split(_BATCH_DELIMITER)):
            key, _, message = entry.partition("=")
            if key:
                errors[key] = message
    return errors


def _chunks(statements: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    """Split oversized batches: notes reach 10k chars and would blow the arg limit."""
    chunks, current, size = [], [], 0
    for item in statements:
        cost = len(item[1]) + 200
        if current and size + cost > _MAX_BATCH_CHARS:
            chunks.append(current)
            current, size = [], 0
        current.append(item)
        size += cost
    if current:
        chunks.append(current)
    return chunks
