"""The one permission request, made while OrcaSlicer loads the plugin.

This module must stay free of numpy and of anything that imports it: it runs
before the permission is granted, and importing numpy opens about 120 files.
"""

import json
import sys

import orca

RESTART_NOTICE = ("Nut inserter is installed. Restart OrcaSlicer once to finish: the file "
                  "permission you just granted takes effect at the next start. Until then "
                  "the plugin does nothing.")


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


def first_session(capability) -> bool:
    """True in the session in which the plugin was installed, and mark it as seen.

    In OrcaSlicer 2.5.0 the permission granted at install only took effect at the
    next start: in the install session every file Python opened still raised a
    prompt (docs/api-facts.md). A capability's stored config is empty until
    something is saved, so an empty config means "never run before".
    """
    try:
        stored = json.loads(capability.get_config() or "{}")
        if stored:
            return False
        capability.save_config(json.dumps({"activated": True}))
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"Nut inserter: could not read its config: {exc!r}")
        return False


def notify_restart() -> None:
    try:
        orca.host.ui.push_notification(
            orca.host.ui.NotificationLevel.WarningNotificationLevel, RESTART_NOTICE)
    except Exception as exc:  # noqa: BLE001
        print(f"Nut inserter: {RESTART_NOTICE} ({exc!r})")
