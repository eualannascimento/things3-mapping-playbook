import pytest

from things3 import cli, doctor, ops


# --- doctor ----------------------------------------------------------------

def test_summarise_flags_blocking_problems():
    checks = [
        doctor.Check("A", True, "fine"),
        doctor.Check("B", False, "broken", fix="do the thing", required=True),
    ]
    healthy, report = doctor.summarise(checks)
    assert healthy is False
    assert "1 blocking problem" in report
    assert "do the thing" in report, "a failed check must say how to fix it"


def test_optional_check_does_not_block():
    """A missing token only matters for editing existing checklists."""
    checks = [
        doctor.Check("A", True, "fine"),
        doctor.Check("token", False, "not set", required=False),
    ]
    healthy, report = doctor.summarise(checks)
    assert healthy is True
    assert "warn" in report


def test_every_failed_check_carries_a_fix():
    """A diagnostic that only says 'failed' is not a diagnostic."""
    for check in doctor.run_all():
        if not check.ok:
            assert check.fix, f"{check.name} failed without telling the user what to do"


def test_wrap_keeps_lines_within_width():
    lines = doctor._wrap("a " * 60, 20)
    assert all(len(line) <= 20 for line in lines)


def test_trash_check_reports_the_localized_name(monkeypatch):
    """Resolving the Trash by id is what makes this work in any language."""
    monkeypatch.setattr(doctor.applescript, "run", lambda script: type(
        "R", (), {"ok": True, "stdout": "Papierkorb", "stderr": ""})())
    check = doctor._trash_reachable()
    assert check.ok
    assert "Papierkorb" in check.detail


def test_trash_check_fails_when_the_list_cannot_be_resolved(monkeypatch):
    monkeypatch.setattr(doctor.applescript, "run", lambda script: type(
        "R", (), {"ok": False, "stdout": "", "stderr": "-1728"})())
    check = doctor._trash_reachable()
    assert not check.ok
    assert check.fix


# --- cli parsing -----------------------------------------------------------

def test_destructive_commands_default_to_dry_run():
    parser = cli.build_parser()
    assert parser.parse_args(["checklist", "uuid"]).apply is False
    assert parser.parse_args(["delete", "todo", "uuid"]).apply is False


def test_rename_pairs_are_repeatable():
    args = cli.build_parser().parse_args(
        ["checklist", "uuid", "--rename", "a=b", "--rename", "c=d"])
    assert args.rename == ["a=b", "c=d"]


def test_delete_accepts_every_known_kind():
    parser = cli.build_parser()
    for kind in ops.Kind:
        args = parser.parse_args(["delete", kind.name.lower(), "x"])
        assert args.kind == kind.name.lower()


def test_unknown_kind_is_rejected():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["delete", "nonsense", "x"])


def test_command_is_required():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_malformed_rename_pair_is_rejected(capsys):
    """OLD=NEW is the contract; anything else would silently do nothing."""
    code = cli.main(["checklist", "uuid", "--rename", "no-equals-sign"])
    assert code == 2
    assert "OLD=NEW" in capsys.readouterr().err


# --- create/rename/move/status/restore: argparse wiring --------------------

def test_create_accepts_every_known_kind():
    parser = cli.build_parser()
    for kind in ops.Kind:
        args = parser.parse_args(["create", kind.name.lower(), "Title"])
        assert args.kind == kind.name.lower()
        assert args.title == "Title"


def test_rename_defaults_to_addressing_by_uuid():
    args = cli.build_parser().parse_args(["rename", "todo", "uuid", "New title"])
    assert args.by_name is False


def test_move_requires_exactly_one_destination():
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["move", "uuid"])
    with pytest.raises(SystemExit):
        parser.parse_args(["move", "uuid", "--to-list", "Today", "--to-area", "Health"])
    args = parser.parse_args(["move", "uuid", "--to-list", "Today"])
    assert args.to_list == "Today" and args.to_project is None and args.to_area is None


def test_status_rejects_an_unknown_value():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["status", "todo", "uuid", "sleeping"])


def test_status_accepts_every_valid_value():
    parser = cli.build_parser()
    for value in ("open", "completed", "canceled"):
        args = parser.parse_args(["status", "todo", "uuid", value])
        assert args.status == value


def test_restore_defaults_to_list_none_so_ops_uses_its_own_default():
    args = cli.build_parser().parse_args(["restore", "todo", "uuid"])
    assert args.to_list is None


# --- create/rename/move/status/restore: wired to the right ops function ----

def test_create_calls_ops_create_and_prints_the_new_uuid(monkeypatch, capsys):
    monkeypatch.setattr(ops, "create",
                        lambda kind, title: ops.Outcome(True, "new-uuid"))
    code = cli.main(["create", "area", "Health"])
    assert code == 0
    assert "new-uuid" in capsys.readouterr().out


def test_create_reports_an_unsupported_kind(monkeypatch, capsys):
    def _raise(kind, title):
        raise ops.UnsupportedOperation("headings can't be created standalone")
    monkeypatch.setattr(ops, "create", _raise)
    code = cli.main(["create", "heading", "X"])
    assert code == 1
    assert "standalone" in capsys.readouterr().err


def test_move_passes_through_the_chosen_destination(monkeypatch):
    seen = {}
    monkeypatch.setattr(ops, "move", lambda uuid, **kw: (seen.update(kw), ops.Outcome(True, "moved"))[1])
    cli.main(["move", "uuid", "--to-area", "Health"])
    assert seen == {"to_list": None, "to_project": None, "to_area": "Health"}


def test_status_addresses_by_name_when_flagged(monkeypatch):
    seen = {}

    def fake_set_status(kind, identifier, status, *, by_id):
        seen["by_id"] = by_id
        return ops.Outcome(True, status)

    monkeypatch.setattr(ops, "set_status", fake_set_status)
    cli.main(["status", "todo", "Buy bread", "completed", "--by-name"])
    assert seen["by_id"] is False


def test_restore_omits_to_list_when_not_given(monkeypatch):
    seen = {}

    def fake_restore(kind, identifier, **kwargs):
        seen.update(kwargs)
        return ops.Outcome(True, "restored")

    monkeypatch.setattr(ops, "restore", fake_restore)
    cli.main(["restore", "todo", "uuid"])
    assert seen == {}


def test_restore_reports_an_unsupported_kind(monkeypatch, capsys):
    def _raise(kind, identifier, **kwargs):
        raise ops.UnsupportedOperation("areas never reach the Trash")
    monkeypatch.setattr(ops, "restore", _raise)
    code = cli.main(["restore", "area", "Health"])
    assert code == 1
    assert "Trash" in capsys.readouterr().err
