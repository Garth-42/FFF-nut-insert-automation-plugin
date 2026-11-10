"""Stand-in for OrcaSlicer's `orca` module, for plugin-layer tests.

It implements only the calls in the API table of docs/SPEC.md. Test helpers
live in `orca._fake`, which the real module does not have.
"""

from . import _fake, host, pages, script, slicing
from ._base import ExecutionResult, LifecycleEvent, PluginResult

__all__ = ["ExecutionResult", "LifecycleEvent", "PluginResult", "base", "host", "pages",
           "plugin", "register_capability", "request_permissions", "script", "slicing", "_fake"]


class base:  # noqa: N801  (the real module spells it this way)
    def register_capabilities(self):
        pass


def plugin(cls):
    _fake.plugin_classes.append(cls)
    return cls


def register_capability(cls):
    _fake.registered.append(cls)


def request_permissions(fs_read=(), fs_readwrite=(), network_http=(), network_socket=(),
                        process=(), threading=False, network=()):
    _fake.permission_requests.append({"fs_read": list(fs_read),
                                      "fs_readwrite": list(fs_readwrite)})
