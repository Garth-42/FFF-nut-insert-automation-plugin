"""Nut inserter: the OrcaSlicer 2.5 plugin. This is the wheel's entry package.

Three capabilities share one cached report (see state.py):
  CheckNuts  script action, docked panel, model-change handling
  NutsTab    the Nuts tab with the wireframe preview
  NutInsert  slice gate and G-code export step; it also owns the settings

Nothing that needs numpy is imported while Orca loads this module. OrcaSlicer
asks for permission on every file a plugin opens, and importing numpy opens
about 120. The plugin asks once for read access to Python's library folders
(permissions.request), and numpy is first imported inside a capability method,
after Orca has shown that request.
"""

import orca

from . import permissions
from .ui_panel import PANEL_HTML
from .ui_preview import PREVIEW_HTML

__all__ = ["PANEL_HTML", "PREVIEW_HTML", "CheckNuts", "NutInsert", "NutInserterPlugin", "NutsTab"]

permissions.request()

EV = orca.LifecycleEvent
MODEL_EVENTS = (EV.ObjectAdded, EV.ObjectDeleted, EV.ObjectTransformed,
                EV.ObjectChanged, EV.ObjectRenamed, EV.ProjectOpened,
                EV.NewProject, EV.ProjectClosed)


def _call(name, *args):
    """Run state.<name>(*args) guarded. Importing state is what first imports numpy."""
    try:
        from . import state
    except Exception as exc:  # noqa: BLE001  never crash the host
        print(f"Nut inserter could not start: {exc!r}")
        return orca.ExecutionResult.failure(orca.PluginResult.RecoverableError,
                                            f"Nut inserter could not start: {exc}")
    return state.guarded(getattr(state, name), *args)


class CheckNuts(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Check nuts"

    def on_load(self):
        _call("open_panel", PANEL_HTML)

    def execute(self):
        return _call("check_action")

    def on_lifecycle_event(self, event, ctx):
        if event in MODEL_EVENTS:
            _call("model_changed")


class NutsTab(orca.pages.PagesPluginCapabilityBase):
    def get_name(self):
        return "Nuts"

    def get_ui(self):
        return PREVIEW_HTML

    def on_message(self, data):
        _call("on_tab_message", self, data)


class NutInsert(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "Nut insert"

    def get_default_config(self):
        from nutcore import library  # no numpy in this module
        return library.default_config()

    def on_load(self):
        _call("set_config_owner", self)

    def execute(self, ctx):
        if ctx.step == orca.slicing.Step.posSlice:
            return _call("slice_gate")
        if ctx.step == orca.slicing.Step.psGCodePostProcess:
            return _call("export", ctx)
        return orca.ExecutionResult.success()


@orca.plugin
class NutInserterPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(CheckNuts)
        orca.register_capability(NutsTab)
        orca.register_capability(NutInsert)
