"""Command line interface.

Deliberately small. The library is the product; this exists so the capabilities
can be exercised without writing Python, and so `doctor` is one command away.

Anything destructive is dry-run by default and needs `--apply` to write.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import checklist, doctor, ops, read


def _cmd_doctor(_args) -> int:
    checks = doctor.run_all()
    healthy, report = doctor.summarise(checks)
    print("\nthings3-mapping-playbook — environment check\n")
    print(report)
    print()
    return 0 if healthy else 1


def _cmd_show(args) -> int:
    """Print everything about an item, including what AppleScript cannot see."""
    conn = read.connect()
    try:
        row = conn.execute(
            "SELECT uuid, title, notes, status, type FROM TMTask WHERE uuid = ?",
            (args.uuid,),
        ).fetchone()
        if row is None:
            print(f"No item with uuid {args.uuid}", file=sys.stderr)
            return 1
        payload = dict(row)
        payload["checklist"] = [
            {"title": i["title"], "completed": i["status"] == read.STATUS_COMPLETED}
            for i in read.checklist_items(conn, args.uuid)
        ]
        payload["recurrence"] = read.recurrence(conn, args.uuid)
        payload["is_repeating"] = read.is_repeating(conn, args.uuid)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        conn.close()


def _cmd_checklist(args) -> int:
    """Edit checklist items -- the operation with no direct API."""
    renames = {}
    for pair in args.rename or []:
        if "=" not in pair:
            print(f"--rename expects OLD=NEW, got {pair!r}", file=sys.stderr)
            return 2
        old, new = pair.split("=", 1)
        renames[old] = new

    conn = read.connect()
    try:
        plan = checklist.plan(conn, args.uuid, rename=renames, remove=args.remove or [])
        if not plan.changed:
            print("Nothing to change.")
            return 0

        print(f"Task: {plan.task_title}")
        print("  before:", [i["title"] for i in plan.before])
        print("  after: ", [i["title"] for i in plan.after])

        if not args.apply:
            print("\nDry run. Re-run with --apply to write "
                  "(needs THINGS_AUTH_TOKEN).")
            return 0

        checklist.apply(conn, plan)
        print(f"\nApplied. Backup: {plan.backup_path}")
        print("Verified against the database.")
        return 0
    finally:
        conn.close()


def _cmd_create(args) -> int:
    try:
        outcome = ops.create(ops.Kind[args.kind.upper()], args.title)
    except ops.UnsupportedOperation as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(outcome.detail)
    return 0 if outcome.ok else 1


def _cmd_rename(args) -> int:
    try:
        outcome = ops.rename(ops.Kind[args.kind.upper()], args.identifier, args.new_title,
                             by_id=not args.by_name)
    except ops.UnsupportedOperation as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(outcome.detail)
    return 0 if outcome.ok else 1


def _cmd_move(args) -> int:
    outcome = ops.move(args.uuid, to_list=args.to_list, to_project=args.to_project,
                       to_area=args.to_area)
    print(outcome.detail)
    return 0 if outcome.ok else 1


def _cmd_status(args) -> int:
    try:
        outcome = ops.set_status(ops.Kind[args.kind.upper()], args.identifier, args.status,
                                 by_id=not args.by_name)
    except ops.UnsupportedOperation as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(outcome.detail)
    return 0 if outcome.ok else 1


def _cmd_restore(args) -> int:
    try:
        kwargs = {"to_list": args.to_list} if args.to_list else {}
        outcome = ops.restore(ops.Kind[args.kind.upper()], args.identifier, **kwargs)
    except ops.UnsupportedOperation as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(outcome.detail)
    return 0 if outcome.ok else 1


def _cmd_delete(args) -> int:
    conn = read.connect()
    try:
        kind = ops.Kind[args.kind.upper()]
        if not args.apply:
            print(f"Would delete {kind.name.lower()} {args.identifier}.")
            if kind in ops.IRREVERSIBLE_DELETE:
                print("  This type is deleted permanently -- it does not reach the Trash.")
                print("  --apply alone is not enough; add --allow-irreversible.")
            else:
                print("  Goes to the native Trash; restorable.")
            return 0
        outcome = ops.delete(conn, kind, args.identifier, by_id=not args.by_name,
                             allow_irreversible=args.allow_irreversible)
        print(outcome.detail)
        if outcome.backup_path:
            print(f"Backup: {outcome.backup_path}")
        return 0 if outcome.ok else 1
    except (ops.ConfirmationRequired, ops.UnsupportedOperation) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="things3",
        description="Safe automation for Things 3, with the guarantees the platform lacks.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="check the environment and report what to fix").set_defaults(
        func=_cmd_doctor)

    show = sub.add_parser("show", help="print an item with its checklist and recurrence")
    show.add_argument("uuid")
    show.set_defaults(func=_cmd_show)

    cl = sub.add_parser("checklist", help="edit checklist items of an existing to-do")
    cl.add_argument("uuid")
    cl.add_argument("--rename", action="append", metavar="OLD=NEW",
                    help="rename an item; repeatable")
    cl.add_argument("--remove", action="append", metavar="TITLE",
                    help="remove an item; repeatable")
    cl.add_argument("--apply", action="store_true", help="write the change (default: dry run)")
    cl.set_defaults(func=_cmd_checklist)

    cr = sub.add_parser("create", help="create a to-do, project, area or tag")
    cr.add_argument("kind", choices=[k.name.lower() for k in ops.Kind])
    cr.add_argument("title")
    cr.set_defaults(func=_cmd_create)

    rn = sub.add_parser("rename", help="rename any item, including a heading")
    rn.add_argument("kind", choices=[k.name.lower() for k in ops.Kind])
    rn.add_argument("identifier", help="uuid by default; a title with --by-name")
    rn.add_argument("new_title")
    rn.add_argument("--by-name", action="store_true", help="identifier is a title, not a uuid")
    rn.set_defaults(func=_cmd_rename)

    mv = sub.add_parser("move", help="move a to-do to a list, project or area")
    mv.add_argument("uuid")
    dest = mv.add_mutually_exclusive_group(required=True)
    dest.add_argument("--to-list", help="a built-in list name or id, e.g. Today")
    dest.add_argument("--to-project", help="destination project title")
    dest.add_argument("--to-area", help="destination area title")
    mv.set_defaults(func=_cmd_move)

    st = sub.add_parser("status", help="complete, cancel or reopen a to-do, project or heading")
    st.add_argument("kind", choices=[k.name.lower() for k in ops.Kind])
    st.add_argument("identifier", help="uuid by default; a title with --by-name")
    st.add_argument("status", choices=["open", "completed", "canceled"])
    st.add_argument("--by-name", action="store_true", help="identifier is a title, not a uuid")
    st.set_defaults(func=_cmd_status)

    rs = sub.add_parser("restore", help="bring a to-do or project back from the Trash")
    rs.add_argument("kind", choices=[k.name.lower() for k in ops.Kind])
    rs.add_argument("identifier")
    rs.add_argument("--to-list", help="default: Anytime")
    rs.set_defaults(func=_cmd_restore)

    dl = sub.add_parser("delete", help="delete an item, with the guard its type deserves")
    dl.add_argument("kind", choices=[k.name.lower() for k in ops.Kind])
    dl.add_argument("identifier")
    dl.add_argument("--by-name", action="store_true", help="identifier is a title, not a uuid")
    dl.add_argument("--apply", action="store_true", help="write the change (default: dry run)")
    dl.add_argument("--allow-irreversible", action="store_true",
                    help="required for areas and tags, which never reach the Trash")
    dl.set_defaults(func=_cmd_delete)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
