"""Shared pieces of the stand-in orca module."""

import enum
import json


class PluginResult(enum.Enum):
    Success = 0
    Skipped = 1
    RecoverableError = 2
    FatalError = 3


class ExecutionResult:
    def __init__(self, status, message="", data=""):
        self.status, self.message, self.data = status, message, data

    @classmethod
    def success(cls, message="", data=""):
        return cls(PluginResult.Success, message, data)

    @classmethod
    def skipped(cls, message=""):
        return cls(PluginResult.Skipped, message)

    @classmethod
    def failure(cls, status, message, data=""):
        return cls(status, message, data)

    def __repr__(self):
        return f"ExecutionResult({self.status.name}, {self.message!r})"


class LifecycleEvent(enum.Enum):
    ObjectAdded = 1
    ObjectDeleted = 2
    ObjectTransformed = 3
    ObjectChanged = 4
    ObjectRenamed = 5
    ProjectOpened = 6
    NewProject = 7
    ProjectClosed = 8
    SliceCompleted = 99   # an event the plugin does not use


class CapabilityBase:
    """Settings are stored per capability as a JSON string, like Orca does."""

    _saved = None

    def get_name(self):
        return type(self).__name__

    def get_default_config(self):
        return {}

    def get_config(self):
        # Like Orca: "{}" until something has been saved. The defaults are not applied.
        return self._saved if self._saved is not None else "{}"

    def save_config(self, text):
        json.loads(text)
        self._saved = text
        return True

    def on_load(self):
        pass

    def on_unload(self):
        pass

    def on_lifecycle_event(self, event, ctx):
        pass
