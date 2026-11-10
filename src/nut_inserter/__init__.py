"""Nut inserter: the OrcaSlicer 2.5 plugin. This is the wheel's entry package.

Three capabilities share one cached report (see state.py):
  CheckNuts  script action, docked panel, model-change handling
  NutsTab    the Nuts tab with the wireframe preview
  NutInsert  slice gate and G-code export step; it also owns the settings
"""

import orca

from nutcore import library

from . import state
from .ui_panel import PANEL_HTML
from .ui_preview import PREVIEW_HTML

EV = orca.LifecycleEvent
MODEL_EVENTS = (EV.ObjectAdded, EV.ObjectDeleted, EV.ObjectTransformed,
                EV.ObjectChanged, EV.ObjectRenamed, EV.ProjectOpened,
                EV.NewProject, EV.ProjectClosed)


class CheckNuts(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Check nuts"

    def on_load(self):
        state.guarded(state.open_panel, PANEL_HTML)

    def execute(self):
        return state.guarded(state.check_action)

    def on_lifecycle_event(self, event, ctx):
        if event in MODEL_EVENTS:
            state.guarded(state.model_changed)


class NutsTab(orca.pages.PagesPluginCapabilityBase):
    def get_name(self):
        return "Nuts"

    def get_ui(self):
        return PREVIEW_HTML

    def on_message(self, data):
        state.guarded(state.on_tab_message, self, data)


class NutInsert(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "Nut insert"

    def get_default_config(self):
        return library.default_config()

    def on_load(self):
        state.config_owner = self

    def execute(self, ctx):
        if ctx.step == orca.slicing.Step.posSlice:
            return state.guarded(state.slice_gate)
        if ctx.step == orca.slicing.Step.psGCodePostProcess:
            return state.guarded(state.export, ctx)
        return orca.ExecutionResult.success()


@orca.plugin
class NutInserterPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(CheckNuts)
        orca.register_capability(NutsTab)
        orca.register_capability(NutInsert)
