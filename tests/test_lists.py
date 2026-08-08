"""The list ids are the reason this library works in any language."""
import re

import pytest

from things3 import lists, ops


def test_specifier_addresses_by_id_not_by_name():
    assert lists.specifier(lists.TRASH) == 'list id "TMTrashListSource"'


def test_english_names_map_to_ids():
    assert lists.BY_ENGLISH_NAME["Trash"] == lists.TRASH
    assert lists.BY_ENGLISH_NAME["Anytime"] == lists.ANYTIME


def test_no_library_code_addresses_a_list_by_name():
    """A literal `list "Name"` is a defect: display names are localized."""
    from pathlib import Path

    package = Path(lists.__file__).parent
    offenders = []
    for path in package.rglob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r'list\s+"(?!\s*\{)', line) and "list id" not in line:
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert not offenders, "address these by id instead:\n" + "\n".join(offenders)


def test_a_caller_passing_an_english_name_still_reaches_the_id():
    assert ops._list_specifier("Anytime") == 'list id "TMNextListSource"'


def test_a_caller_passing_an_id_is_left_alone():
    assert ops._list_specifier(lists.TODAY) == 'list id "TMTodayListSource"'
