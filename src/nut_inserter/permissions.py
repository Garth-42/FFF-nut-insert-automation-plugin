"""The one permission request, made while OrcaSlicer loads the plugin.

This module must stay free of numpy and of anything that imports it: it runs
before the permission is granted, and importing numpy opens about 120 files.
"""

import sys

import orca


def targets() -> list[str]:
    """Read access to Python's own library folders: everything on sys.path.

    OrcaSlicer asks for permission each time a plugin opens a file, and that
    includes the files Python reads to import a module (docs/api-facts.md).
    A target ending in "/*" grants a whole folder tree.
    """
    found = []
    for entry in sys.path:
        entry = entry.rstrip("/\\")
        if not entry:
            continue
        is_file = entry.lower().endswith((".zip", ".py", ".whl", ".egg"))
        found.append(entry if is_file else entry + "/*")
    return found


def request() -> None:
    """Ask once. Orca shows one request for all targets after the plugin has registered."""
    try:
        orca.request_permissions(fs_read=targets())
    except Exception as exc:  # noqa: BLE001  an Orca without the call still loads the plugin
        print(f"Nut inserter: request_permissions failed: {exc!r}")
