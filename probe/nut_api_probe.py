# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy"]
#
# [tool.orcaslicer.plugin]
# name = "Nut API probe"
# description = "Shows what the plugin API exposes. Changes nothing, opens no files."
# author = "nut-inserter"
# version = "0.6.1"
# ///
"""Nut API probe for OrcaSlicer 2.5.

It changes nothing, opens no files itself and prints nothing. Everything is
kept in memory and shown in the "Nut probe" tab, where you can copy it.

The steps are separate script actions, ordered from harmless to "may raise
permission prompts", so the output shows which call Orca objects to.
See docs/manual-test.md.
"""

import sys
import threading

import orca

PREFIX = "NUTPROBE"
MAX_PER_EVENT = 2      # keep each kind of lifecycle event this many times
MAX_LINES = 4000

LINES = []             # the probe's whole output, in memory


def log(*parts):
    if len(LINES) < MAX_LINES:
        LINES.append(" ".join([PREFIX, *[str(p) for p in parts]]))


def log_error(where, exc):
    """Record an exception without the traceback module, which reads source files."""
    tb = exc.__traceback__
    line = "?"
    while tb is not None:
        line = tb.tb_lineno
        tb = tb.tb_next
    log(where, "FAILED at probe line", line, repr(exc))


def safe(label, fn):
    """Run fn and record its result. A probe must never raise into Orca."""
    try:
        log(label, "=", fn())
    except Exception as exc:  # noqa: BLE001
        log(label, "FAILED", repr(exc))


def step(label, fn):
    """Run fn, record its result and which Python modules it caused to be imported.

    Importing a module opens files, and Orca prompts for each one, so this
    shows which call is behind a flood of prompts. It opens nothing itself.
    The line before the call is written first, so a call that never returns
    still leaves its name in the output.
    """
    before = set(sys.modules)
    log("call", label)
    try:
        value = fn()
        shown = repr(value)
        log("  ->", shown if len(shown) < 300 else shown[:300] + "...")
    except Exception as exc:  # noqa: BLE001
        log("  -> FAILED", repr(exc))
        value = None
    new = sorted(set(sys.modules) - before)
    if new:
        log("  -> imported", len(new), "modules:", new[:30])
    return value


def names(obj):
    return sorted(n for n in dir(obj) if not n.startswith("__"))


def thread_name():
    return threading.current_thread().name


def doc(label, getter, limit=700):
    """Record a docstring. pybind11 puts the call signature in it."""
    try:
        text = " | ".join(str(getter().__doc__ or "").split("\n"))
        log("doc", label, "=", text[:limit])
    except Exception as exc:  # noqa: BLE001
        log("doc", label, "FAILED", repr(exc))


def doc_members(owner_label, owner, limit=400):
    if owner is None:
        log("doc", owner_label, "is missing")
        return
    try:
        for member in names(owner):
            if not member.startswith("_"):
                doc(f"{owner_label}.{member}", lambda m=member: getattr(owner, m), limit)
    except Exception as exc:  # noqa: BLE001
        log("doc", owner_label, "FAILED", repr(exc))


def dump_docs():
    """Signatures the earlier runs did not capture, or captured cut short."""
    log("== docs, round 2 ==")
    doc("orca.request_permissions", lambda: orca.request_permissions, limit=6000)
    doc("orca.host.ui.create_dock_panel", lambda: orca.host.ui.create_dock_panel, limit=3000)
    for name in ("UiDockPanel", "UiWindow"):
        safe("dir orca.host.ui." + name, lambda n=name: names(getattr(orca.host.ui, n)))
        doc_members("orca.host.ui." + name, getattr(orca.host.ui, name, None))
    safe("dir orca.host.BoundingBox", lambda: names(orca.host.BoundingBox))
    for name in ("TriangleMesh", "ModelVolume", "ModelInstance", "BoundingBox", "Layer",
                 "Print", "PrintObject"):
        doc_members("orca.host." + name, getattr(orca.host, name, None))
    safe("dir SlicingPipelineContext", lambda: names(orca.slicing.SlicingPipelineContext))
    doc_members("SlicingPipelineContext", getattr(orca.slicing, "SlicingPipelineContext", None))
    doc_members("LifecycleEventContext", getattr(orca, "LifecycleEventContext", None))
    doc_members("PythonPluginBase", getattr(orca, "PythonPluginBase", None), limit=600)
    doc("orca.slicing.unscale", lambda: orca.slicing.unscale)
    doc("orca.host.plugin", lambda: orca.host.plugin, limit=1500)
    safe("dir orca.host.plugin", lambda: names(orca.host.plugin))
    safe("app_info", lambda: orca.host.app_info())
    safe("sys.version", lambda: sys.version)
    safe("numpy already loaded", lambda: "numpy" in sys.modules)
    safe("sys.path", lambda: list(sys.path))


def first_volume():
    return orca.host.model().objects()[0].volumes()[0]


def dump_model():
    """Names, types and plate index, one call at a time. Nothing here should need numpy."""
    log("== model, thread", thread_name(), "==")
    model = step("host.model()", orca.host.model)
    if model is None:
        return
    step("model.object_count()", lambda: model.object_count())
    step("model.current_plate_index()", lambda: model.current_plate_index())
    objects = step("model.objects()", model.objects) or []
    for oi, obj in enumerate(objects):
        step(f"object {oi} name", lambda o=obj: o.name)
        step(f"object {oi} printable", lambda o=obj: o.printable)
        step(f"object {oi} instance_count()", lambda o=obj: o.instance_count())
        volumes = step(f"object {oi} volumes()", obj.volumes) or []
        for vi, vol in enumerate(volumes):
            where = f"object {oi} volume {vi}"
            step(where + " name", lambda v=vol: v.name)
            step(where + " type()", lambda v=vol: v.type())
            step(where + " is_modifier()", lambda v=vol: v.is_modifier())
            step(where + " is_model_part()", lambda v=vol: v.is_model_part())
            step(where + " facets_count()", lambda v=vol: v.facets_count())


def dump_transforms():
    """Matrices and offsets, one call at a time. These may return numpy arrays."""
    log("== transforms, thread", thread_name(), "==")
    obj = orca.host.model().objects()[0]
    vol, inst = obj.volumes()[0], obj.instances()[0]
    step("instance.is_left_handed()", inst.is_left_handed)
    for label, target in (("volume", vol), ("instance", inst)):
        for member in ("bounding_box", "scaling_factor", "mirror", "offset", "rotation"):
            step(f"{label}.{member}", lambda t=target, m=member: _value(getattr(t, m)))
    matrix = step("volume.matrix()", vol.matrix)
    step("type(volume.matrix())", lambda: type(matrix).__name__)
    step("instance.matrix()", inst.matrix)


def dump_mesh_plain():
    """One mesh through the accessors that should not need numpy arrays."""
    log("== mesh, plain accessors, thread", thread_name(), "==")
    mesh = step("volume.mesh()", first_volume().mesh)
    if mesh is None:
        return
    for member in ("vertex_count", "triangle_count", "facets_count", "is_empty", "volume",
                   "bounding_box"):
        step(f"mesh.{member}", lambda m=member: _value(getattr(mesh, m)))
    vertex = step("mesh.vertex(0)", lambda: mesh.vertex(0))
    step("type(mesh.vertex(0))", lambda: type(vertex).__name__)
    step("list(mesh.vertex(0))", lambda: [float(c) for c in vertex])
    triangle = step("mesh.triangle(0)", lambda: mesh.triangle(0))
    step("type(mesh.triangle(0))", lambda: type(triangle).__name__)


def dump_numpy():
    log("== import numpy, thread", thread_name(), "==")
    step("numpy already loaded", lambda: "numpy" in sys.modules)
    step("sys.path", lambda: list(sys.path))
    numpy = step("import numpy", lambda: __import__("numpy"))
    if numpy is not None:
        step("numpy.__version__", lambda: numpy.__version__)
        step("numpy.__file__", lambda: numpy.__file__)


def dump_mesh_arrays():
    log("== mesh arrays, thread", thread_name(), "==")
    mesh = step("volume.mesh()", first_volume().mesh)
    if mesh is None:
        return
    verts = step("mesh.vertices()", lambda: mesh.vertices())
    tris = step("mesh.triangles()", lambda: mesh.triangles())
    step("mesh.face_normals()", lambda: mesh.face_normals())
    if verts is not None:
        step("vertices shape, dtype, writeable",
             lambda: (verts.shape, str(verts.dtype), bool(verts.flags.writeable)))
        step("vertices bounds", lambda: (verts.min(axis=0).tolist(), verts.max(axis=0).tolist()))
    if tris is not None:
        step("triangles shape, dtype", lambda: (tris.shape, str(tris.dtype)))


def _value(attr):
    return attr() if callable(attr) else attr


def dump_ctx(ctx):
    for name in names(ctx):
        try:
            value = getattr(ctx, name)
            if callable(value):
                log("  ctx." + name, "(callable)")
            else:
                log("  ctx." + name, "=", repr(value)[:300])
        except Exception as exc:  # noqa: BLE001
            log("  ctx." + name, "FAILED", repr(exc))


def run_script(name, fn):
    """Body of every script action. Never raises."""
    try:
        log("script", name, "thread", thread_name())
        fn()
        return orca.ExecutionResult.success(
            name + " recorded. Open the Nut probe tab, press Refresh and copy the output.")
    except Exception as exc:  # noqa: BLE001
        log_error("script " + name, exc)
        return orca.ExecutionResult.failure(orca.PluginResult.RecoverableError, str(exc))


class Probe1(orca.script.ScriptPluginCapabilityBase):
    _event_counts = {}

    def get_name(self):
        return "Nut probe 1: signatures"

    def on_load(self):
        log("on_load, thread", thread_name())

    def execute(self):
        return run_script("1 signatures", dump_docs)

    def on_lifecycle_event(self, event, ctx):
        try:
            seen = self._event_counts.get(str(event), 0)
            self._event_counts[str(event)] = seen + 1
            if seen >= MAX_PER_EVENT:
                return
            log("event", event, "thread", thread_name())
            if ctx is not None:
                dump_ctx(ctx)
        except Exception as exc:  # noqa: BLE001
            log_error("event", exc)


class Probe2(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Nut probe 2: model names and types"

    def execute(self):
        return run_script("2 model", dump_model)


class Probe3(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Nut probe 3: mesh without arrays"

    def execute(self):
        return run_script("3 mesh plain", dump_mesh_plain)


class Probe4(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Nut probe 4: transforms (may prompt)"

    def execute(self):
        return run_script("4 transforms", dump_transforms)


class Probe5(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Nut probe 5: import numpy (may prompt)"

    def execute(self):
        return run_script("5 numpy", dump_numpy)


class Probe6(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Nut probe 6: mesh arrays (may prompt)"

    def execute(self):
        return run_script("6 mesh arrays", dump_mesh_arrays)


PAGE = """<!doctype html><html><body style="font-family:sans-serif;padding:12px;margin:0">
<h3 style="margin:0 0 8px">Nut API probe</h3>
<p style="margin:0 0 8px">Press Refresh after each step, then Select all and copy the text.</p>
<button id="refresh">Refresh</button> <button id="select">Select all</button>
<button id="clear">Clear</button> <span id="state"></span>
<textarea id="out" readonly spellcheck="false"
  style="display:block;width:100%;height:75vh;margin-top:8px;font:12px monospace"></textarea>
<script>
var out = document.getElementById('out'), state = document.getElementById('state');
function start() {
  if (!window.orca) { state.textContent = 'window.orca missing, retrying'; setTimeout(start, 200); return; }
  window.orca.onMessage(function (m) {
    if (typeof m === 'string') { try { m = JSON.parse(m); } catch (e) { return; } }
    if (m && m.text != null) { out.value = m.text; state.textContent = 'Updated ' + new Date().toLocaleTimeString(); }
  });
  window.orca.postMessage({type: 'ready'});
}
document.getElementById('refresh').onclick = function () { window.orca.postMessage({type: 'refresh'}); };
document.getElementById('clear').onclick = function () { window.orca.postMessage({type: 'clear'}); };
document.getElementById('select').onclick = function () { out.focus(); out.select(); };
start();
</script></body></html>"""


class ProbePage(orca.pages.PagesPluginCapabilityBase):
    def get_name(self):
        return "Nut probe"

    def get_ui(self):
        return PAGE

    def on_message(self, data):
        try:
            if isinstance(data, dict) and data.get("type") == "clear":
                LINES.clear()
            self.post_message({"type": "log", "text": "\n".join(LINES)})
        except Exception as exc:  # noqa: BLE001
            log_error("page", exc)


class ProbeSlicing(orca.slicing.SlicingPipelineCapabilityBase):
    _seen = set()

    def get_name(self):
        return "Nut probe: slicing"

    def execute(self, ctx):
        try:
            current = ctx.step
            if str(current) not in self._seen:
                self._seen.add(str(current))
                log("== slicing step", current, "thread", thread_name(), "==")
                dump_ctx(ctx)
                for key in ("gcode_flavor", "print_sequence", "layer_height", "curr_bed_type"):
                    step(f"config_value {key}", lambda k=key: ctx.config_value(k))
                step("model names from slicing thread", lambda: [
                    (obj.name, [v.name for v in obj.volumes()])
                    for obj in orca.host.model().objects()])
                if current == orca.slicing.Step.psGCodePostProcess:
                    log("gcode_path =", repr(ctx.gcode_path))
        except Exception as exc:  # noqa: BLE001
            log_error("slicing", exc)
        return orca.ExecutionResult.success()


@orca.plugin
class NutApiProbe(orca.base):
    def register_capabilities(self):
        for capability in (Probe1, Probe2, Probe3, Probe4, Probe5, Probe6, ProbePage,
                           ProbeSlicing):
            orca.register_capability(capability)
