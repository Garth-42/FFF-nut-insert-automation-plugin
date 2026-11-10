"""Name matching: which parts are nuts, and which library entry they use."""

from __future__ import annotations

import re

# "NUT_" at the start of the name or after a character that is not a letter or digit.
_PREFIX = re.compile(r"(?<![A-Za-z0-9])NUT_", re.IGNORECASE)


def looks_like_nut(name: str) -> bool:
    """True when the name contains a NUT_ marker, whether or not a library key follows."""
    return _PREFIX.search(name) is not None


def match_key(name: str, keys) -> str | None:
    """Return the library key a part name refers to, or None.

    The key must follow NUT_ directly and end at the end of the name or at a
    character that is not a letter or digit. Case is ignored and the longest
    key that fits wins.
    """
    ordered = sorted(keys, key=len, reverse=True)
    for found in _PREFIX.finditer(name):
        rest = name[found.end():]
        for key in ordered:
            if rest[:len(key)].upper() != key.upper():
                continue
            after = rest[len(key):len(key) + 1]
            if not after or not after.isalnum():
                return key
    return None
