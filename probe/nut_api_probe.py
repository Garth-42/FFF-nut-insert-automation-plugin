# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy"]
#
# [tool.orcaslicer.plugin]
# name = "Nut API probe"
# description = "Shows what the plugin API exposes. Changes nothing, opens no files."
# author = "nut-inserter"
# version = "0.5.0"
# ///
"""Nut API probe for OrcaSlicer 2.5.

It changes nothing and, by default, opens no files and prints nothing: in
OrcaSlicer 2.5.0 every file a plugin opens raises a permission prompt, and
print() appears to count. Everything is kept in memory instead and shown in
the "Nut probe" tab, where you can copy it. See docs/manual-test.md.
"""

import sys
import threading

import orca

PREFIX = "NUTPROBE"
PRINT = False          # True also prints each line; in 2.5.0 that raised a prompt per line
READ_GCODE = False     # True reads the exported G-code once; that opens one file
MAX_PER_EVENT = 2      # keep each kind of lifecycle event this many times
MAX_LINES = 4000

LINES = []             # the probe's whole output, in memory


def log(*parts):
    if len(LINES) < MAX_LINES:
        LINES.append(" ".join([PREFIX, *[str(p) for p in parts]]))
    if PRINT:
        print(PREFIX, *parts, flush=True)


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


def modules_step(label, fn):
    """Run fn and record which Python modules it caused to be imported.

    Importing a module opens files, and Orca prompts for each one, so this
    shows which call is behind a flood of prompts. It opens nothing itself.
    """
    before = set(sys.modules)
    log(">>", label, "| numpy loaded before:", "numpy" in before)
    try:
        value = fn()
    except Exception as exc:  # noqa: BLE001
        log_error(label, exc)
        value = None
    new = sorted(set(sys.modules) - before)
    log("<<", label, "| new modules:", len(new), new[:40])
    return value


def names(obj):
    return sorted(n for n in dir(obj) if not n.startswith("__"))


def thread_name():
    return threading.current_thread().name


def dump_api():
    log("== api ==")
    safe("dir orca", lambda: names(orca))
    safe("dir orca.host", lambda: names(orca.host))
    safe("dir orca.host.ui", lambda: names(orca.host.ui))
    safe("dir orca.slicing.Step", lambda: names(orca.slicing.Step))
    safe("dir orca.LifecycleEvent", lambda: names(orca.LifecycleEvent))
    safe("dir orca.ExecutionResult", lambda: names(orca.ExecutionResult))
    safe("dir orca.PluginResult", lambda: names(orca.PluginResult))


def doc(label, getter):
    """Record a docstring. pybind11 puts the call signature in it."""
    try:
        text = " | ".join(str(getter().__doc__ or "").split("\n"))
        log("doc", label, "=", text[:600])
    except Exception as exc:  # noqa: BLE001
        log("doc", label, "FAILED", repr(exc))


def dump_docs():
    """Signatures and members of things the first probe run found but the docs do not list."""
    log("== docs ==")
    for name in ("request_permissions", "register_capability"):
        doc("orca." + name, lambda n=name: getattr(orca, n))
    for name in ("model", "plater", "plugin", "preset_bundle", "app_info", "selected_printer"):
        doc("orca.host." + name, lambda n=name: getattr(orca.host, n))
    for name in ("create_dock_panel", "create_window", "push_notification", "message"):
        doc("orca.host.ui." + name, lambda n=name: getattr(orca.host.ui, n))
    for name in ("Model", "ModelObject", "ModelVolume", "ModelVolumeType", "ModelInstance",
                 "TriangleMesh", "Plater", "Print", "PrintObject", "Layer"):
        safe("dir orca.host." + name, lambda n=name: names(getattr(orca.host, n)))
    for name in ("PluginContext", "LifecycleEventContext", "PluginType", "SlicingPipeline",
                 "Script", "Pages", "PythonPluginBase"):
        safe("dir orca." + name, lambda n=name: names(getattr(orca, n)))
    for name in ("ScriptPluginCapabilityBase",):
        safe("dir orca.script." + name, lambda n=name: names(getattr(orca.script, n)))
    safe("dir orca.slicing", lambda: names(orca.slicing))
    safe("dir orca.pages", lambda: names(orca.pages))
    for cls, members in (("ModelVolume", ("type", "is_modifier", "is_model_part", "name")),
                         ("Plater", None), ("Model", None), ("ModelObject", None)):
        try:
            target = getattr(orca.host, cls)
            for member in members or names(target):
                doc(f"orca.host.{cls}.{member}", lambda t=target, m=member: getattr(t, m))
        except Exception as exc:  # noqa: BLE001
            log("doc", cls, "FAILED", repr(exc))


def dump_model(where, with_mesh=False):
    """Record names, matrices and types. Meshes only on request: they need numpy."""
    log("== model from", where, "thread", thread_name(), "==")
    try:
        objects = list(orca.host.model().objects())
    except Exception as exc:  # noqa: BLE001
        log("model read FAILED", repr(exc))
        return
    log("object count =", len(objects))
    for oi, obj in enumerate(objects):
        try:
            volumes = list(obj.volumes())
            instances = list(obj.instances())
            if oi == 0:
                log("dir object =", names(obj))
                if volumes:
                    log("dir volume =", names(volumes[0]))
                if instances:
                    log("dir instance =", names(instances[0]))
            log("object", oi, "volumes", len(volumes), "instances", len(instances))
            for vi, vol in enumerate(volumes):
                log("object", oi, "volume", vi, "name =", repr(vol.name))
                if oi == 0 and vi == 0:
                    modules_step("vol.matrix()", lambda v=vol: log("  matrix type",
                                                                   type(v.matrix()).__name__))
                safe("  volume matrix", lambda v=vol: v.matrix().tolist())
                # Part type is not documented. Record anything that looks like it.
                for attr in names(vol):
                    if "type" in attr.lower() or "modifier" in attr.lower():
                        safe(f"  volume.{attr}", lambda v=vol, a=attr: _value(getattr(v, a)))
                if with_mesh and oi == 0 and vi == 0:
                    dump_mesh(vol)
            for ii, inst in enumerate(instances):
                safe(f"object {oi} instance {ii} matrix", lambda i=inst: i.matrix().tolist())
                safe(f"object {oi} instance {ii} left handed", lambda i=inst: i.is_left_handed())
        except Exception as exc:  # noqa: BLE001
            log_error(f"object {oi}", exc)


def dump_mesh(vol):
    """One call at a time, so the log shows which one imports modules or fails."""
    mesh = modules_step("vol.mesh()", vol.mesh)
    if mesh is None:
        return
    safe("dir mesh", lambda: names(mesh))
    verts = modules_step("mesh.vertices()", mesh.vertices)
    tris = modules_step("mesh.triangles()", mesh.triangles)
    if verts is not None:
        safe("vertices type", lambda: type(verts).__name__)
        safe("vertices shape dtype", lambda: (verts.shape, str(verts.dtype)))
        safe("vertices writeable", lambda: bool(verts.flags.writeable))
        modules_step("verts.min/max", lambda: log("bounds =", verts.min(axis=0).tolist(),
                                                  verts.max(axis=0).tolist()))
    if tris is not None:
        safe("triangles shape dtype", lambda: (tris.shape, str(tris.dtype)))


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


def result(text):
    return orca.ExecutionResult.success(text + " Open the Nut probe tab to copy the output.")


class ProbeApi(orca.script.ScriptPluginCapabilityBase):
    """Step 1: the API surface only. Touches neither the model nor numpy."""

    _event_counts = {}

    def get_name(self):
        return "Nut API probe: 1 API"

    def on_load(self):
        try:
            log("on_load script capability, thread", thread_name())
        except Exception as exc:  # noqa: BLE001
            log_error("on_load", exc)

    def execute(self):
        try:
            log("script 1 execute, thread", thread_name())
            dump_api()
            dump_docs()
            return result("API recorded.")
        except Exception as exc:  # noqa: BLE001
            log_error("script 1", exc)
            return orca.ExecutionResult.failure(orca.PluginResult.RecoverableError, str(exc))

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


class ProbeModel(orca.script.ScriptPluginCapabilityBase):
    """Step 2: names, matrices and types. No meshes."""

    def get_name(self):
        return "Nut API probe: 2 model, no meshes"

    def execute(self):
        try:
            log("script 2 execute, thread", thread_name())
            modules_step("whole step 2", lambda: dump_model("script"))
            return result("Model recorded.")
        except Exception as exc:  # noqa: BLE001
            log_error("script 2", exc)
            return orca.ExecutionResult.failure(orca.PluginResult.RecoverableError, str(exc))


class ProbeMesh(orca.script.ScriptPluginCapabilityBase):
    """Step 3: one mesh, one call at a time. In 2.5.0 this is where prompts flooded."""

    def get_name(self):
        return "Nut API probe: 3 mesh (may prompt)"

    def execute(self):
        try:
            log("script 3 execute, thread", thread_name())
            volume = orca.host.model().objects()[0].volumes()[0]
            dump_mesh(volume)
            return result("Mesh recorded.")
        except Exception as exc:  # noqa: BLE001
            log_error("script 3", exc)
            return orca.ExecutionResult.failure(orca.PluginResult.RecoverableError, str(exc))


PAGE = """<!doctype html><html><body style="font-family:sans-serif;padding:12px;margin:0">
<h3 style="margin:0 0 8px">Nut API probe</h3>
<p style="margin:0 0 8px">Press Refresh after each step, then Select all and copy the text.</p>
<button id="refresh">Refresh</button> <button id="select">Select all</button>
<span id="state"></span>
<textarea id="out" readonly spellcheck="false"
  style="display:block;width:100%;height:75vh;margin-top:8px;font:12px monospace"></textarea>
<script>
var out = document.getElementById('out'), state = document.getElementById('state');
var page = [];
function show(text) { out.value = page.join('\\n') + '\\n' + text; }
function start() {
  if (!window.orca) { state.textContent = 'window.orca missing, retrying'; setTimeout(start, 200); return; }
  var gl = null;
  try { gl = document.createElement('canvas').getContext('webgl'); } catch (e) {}
  page.push('NUTPROBE page webgl = ' + (!!gl));
  page.push('NUTPROBE page agent = ' + navigator.userAgent);
  window.orca.onMessage(function (m) {
    var kind = typeof m;
    var line = 'NUTPROBE page received a message as ' + kind;
    if (page.indexOf(line) < 0) { page.push(line); }
    if (kind === 'string') { try { m = JSON.parse(m); } catch (e) { return; } }
    if (m && m.text != null) { show(m.text); state.textContent = 'Updated ' + new Date().toLocaleTimeString(); }
  });
  window.orca.postMessage({type: 'ready'});
}
document.getElementById('refresh').onclick = function () { window.orca.postMessage({type: 'refresh'}); };
document.getElementById('select').onclick = function () { out.focus(); out.select(); };
start();
</script></body></html>"""


class ProbePage(orca.pages.PagesPluginCapabilityBase):
    _logged_type = False

    def get_name(self):
        return "Nut probe"

    def get_ui(self):
        log("page get_ui, thread", thread_name())
        return PAGE

    def on_message(self, data):
        try:
            if not self._logged_type:
                ProbePage._logged_type = True
                log("page on_message type", type(data).__name__, "value", repr(data)[:200],
                    "thread", thread_name())
            text = "\n".join(LINES)
            # Whether pages take objects or JSON strings is not documented: try both.
            try:
                self.post_message({"type": "log", "text": text})
            except Exception as exc:  # noqa: BLE001
                log("post_message(dict) FAILED", repr(exc))
            try:
                self.post_message('{"type": "log", "text": ' + _json_string(text) + "}")
            except Exception as exc:  # noqa: BLE001
                log("post_message(str) FAILED", repr(exc))
        except Exception as exc:  # noqa: BLE001
            log_error("page", exc)


def _json_string(text):
    """A JSON string literal, without importing json."""
    out = ['"']
    for ch in text:
        if ch in '"\\':
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\n")
        elif ord(ch) < 32:
            out.append(" ")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


class ProbeSlicing(orca.slicing.SlicingPipelineCapabilityBase):
    _seen = set()

    def get_name(self):
        return "Nut API probe: slicing"

    def get_default_config(self):
        return {"probe": True, "nested": {"list": [1, 2]}}

    def on_load(self):
        try:
            log("on_load slicing capability, thread", thread_name())
            safe("get_config type and value", lambda: (type(self.get_config()).__name__,
                                                       self.get_config()))
        except Exception as exc:  # noqa: BLE001
            log_error("on_load slicing", exc)

    def execute(self, ctx):
        try:
            step = ctx.step
            if str(step) not in self._seen:
                self._seen.add(str(step))
                log("slicing step", step, "thread", thread_name())
                dump_ctx(ctx)
                for key in ("gcode_flavor", "print_sequence", "printable_area", "layer_height"):
                    safe(f"config_value {key}", lambda k=key: repr(ctx.config_value(k)))
                dump_model(f"slicing step {step}")   # no meshes
                if step == orca.slicing.Step.psGCodePostProcess:
                    log("gcode_path =", repr(ctx.gcode_path))
                    if READ_GCODE:
                        self._dump_gcode(ctx)
        except Exception as exc:  # noqa: BLE001
            log_error("slicing", exc)
        return orca.ExecutionResult.success()

    def _dump_gcode(self, ctx):
        with open(ctx.gcode_path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
        log("gcode line count =", len(lines))
        for i, line in enumerate(lines[:60]):
            log(f"gcode {i + 1:6d}: {line}")


@orca.plugin
class NutApiProbe(orca.base):
    def register_capabilities(self):
        orca.register_capability(ProbeApi)
        orca.register_capability(ProbeModel)
        orca.register_capability(ProbeMesh)
        orca.register_capability(ProbePage)
        orca.register_capability(ProbeSlicing)
