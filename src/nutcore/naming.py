"""Name matching: which parts are nuts or heat-set inserts, and which entry they use.

A nut body is named NUT_<key> (a nut library key) and an insert body HEATSET_<key>
(a heat-set profile's insert_key). Both follow the same rule.
"""

from __future__ import annotations

import re

# The marker at the start of the name or after a character that is not a letter or digit.
_PREFIX = re.compile(r"(?<![A-Za-z0-9])NUT_", re.IGNORECASE)
_INSERT_PREFIX = re.compile(r"(?<![A-Za-z0-9])HEATSET_", re.IGNORECASE)


def looks_like_nut(name: str) -> bool:
    """True when the name contains a NUT_ marker, whether or not a library key follows."""
    return _PREFIX.search(name) is not None


def looks_like_insert(name: str) -> bool:
    """True when the name contains a HEATSET_ marker, whether or not a profile key follows."""
    return _INSERT_PREFIX.search(name) is not None


def match_key(name: str, keys) -> str | None:
    """Return the nut library key a part name refers to, or None.

    The key must follow NUT_ directly and end at the end of the name or at a
    character that is not a letter or digit. Case is ignored and the longest
    key that fits wins.
    """
    return _match(name, keys, _PREFIX)


def match_insert_key(name: str, keys) -> str | None:
    """Return the heat-set insert_key a part name refers to, or None. Same rule, HEATSET_."""
    return _match(name, keys, _INSERT_PREFIX)


def _match(name: str, keys, prefix: re.Pattern) -> str | None:
    ordered = sorted(keys, key=len, reverse=True)
    for found in prefix.finditer(name):
        rest = name[found.end():]
        for key in ordered:
            if rest[:len(key)].upper() != key.upper():
                continue
            after = rest[len(key):len(key) + 1]
            if not after or not after.isalnum():
                return key
    return None
