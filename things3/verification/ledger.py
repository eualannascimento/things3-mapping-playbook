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
            "cell": result.get("cell") or previous.get("cell"),
            "grade": result.get("grade") or previous.get("grade"),
            "first_verified": first,
            "last_verified": today,
        }
        if recipe_id in pending:
            pending.remove(recipe_id)

    return Ledger(environment=environment, recipes=recipes,
                  untestable=dict(existing.untestable), pending=pending)
