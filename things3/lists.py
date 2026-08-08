"""Things' built-in lists, addressed by id rather than by name.

A list's `name` is what the user sees, and it is localized -- Things ships nine
languages. Its `id` is not: the same `TMTrashListSource` identifies the Trash
whichever language the app runs in. Addressing by name is therefore a defect
that only shows up on someone else's machine, which is the worst kind.

The ids were read from a real install with `name of every list` alongside
`id of every list`; the two lists correspond positionally.
"""
from __future__ import annotations

INBOX = "TMInboxListSource"
TODAY = "TMTodayListSource"
ANYTIME = "TMNextListSource"
SOMEDAY = "TMSomedayListSource"
LOGBOOK = "TMLogbookListSource"
TRASH = "TMTrashListSource"

#: English display name -> stable id, for callers migrating from names.
BY_ENGLISH_NAME = {
    "Inbox": INBOX,
    "Today": TODAY,
    "Anytime": ANYTIME,
    "Someday": SOMEDAY,
    "Logbook": LOGBOOK,
    "Trash": TRASH,
}


def specifier(list_id: str) -> str:
    """The AppleScript fragment addressing a built-in list.

    Ids are constants defined in this module and never user input, so they are
    interpolated directly; nothing here escapes attacker-controlled text.
    """
    return f'list id "{list_id}"'
