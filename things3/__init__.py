"""A verified map of what Things 3 automation can and cannot do, plus the code to do it safely.

Reading is done through the local SQLite database (read-only), writing through
AppleScript and the URL scheme -- each chosen per operation rather than by
preference. Every capability in this package was executed against a real Things
install and verified by re-reading the result.

See docs/API-MAP.md for the full capability matrix and docs/PLAYBOOK.md for the
exact command behind each one.
"""

from . import applescript, checklist, guards, ops, read, urlscheme

__version__ = "0.3.0"
__all__ = ["applescript", "checklist", "guards", "ops", "read", "urlscheme"]
