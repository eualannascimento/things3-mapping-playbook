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
