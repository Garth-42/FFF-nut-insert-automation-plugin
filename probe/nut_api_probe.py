# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy"]
#
# [tool.orcaslicer.plugin]
# name = "Nut API probe"
# description = "Prints what the plugin API exposes. Changes nothing."
# author = "nut-inserter"
# version = "0.2.0"
# ///
"""Nut API probe for OrcaSlicer 2.5.

It changes nothing. It prints lines that start with NUTPROBE to Orca's Python
log (data folder, log/python_*.log). See docs/manual-test.md for the steps.
"""

import threading

import orca

PREFIX = "NUTPROBE"
MAX_PER_EVENT = 2      # log each kind of lifecycle event this many times, then stay quiet
READ_GCODE = True      # the only file this probe opens: the exported G-code, once


def log(*parts):
    print(PREFIX, *parts, flush=True)


def log_error(where, exc):
    """Log an exception without the traceback module.

    Formatting a traceback makes Python open source files to quote them, and
    Orca asks for permission on every file a plugin opens.
    """
    tb = exc.__traceback__
    line = "?"
    while tb is not None:
        line = tb.tb_lineno
        tb = tb.tb_next
    log(where, "FAILED at probe line", line, repr(exc))


def safe(label, fn):
    """Run fn and log its result. A probe must never raise into Orca."""
    try:
        log(label, "=", fn())
    except Exception as exc:  # noqa: BLE001
        log(label, "FAILED", repr(exc))


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


def dump_model(where):
    """Log everything readable about the model. Used from several threads."""
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
                    safe("dir mesh", lambda v=volumes[0]: names(v.mesh()))
                if instances:
                    log("dir instance =", names(instances[0]))
            log("object", oi, "volumes", len(volumes), "instances", len(instances))
            for vi, vol in enumerate(volumes):
                mesh = vol.mesh()
                verts = mesh.vertices()
                tris = mesh.triangles()
                log("object", oi, "volume", vi, "name =", repr(vol.name))
                log("  vertices", verts.shape, verts.dtype, "triangles", tris.shape, tris.dtype)
                safe("  vertices writeable", lambda v=verts: bool(v.flags.writeable))
                safe("  bounds", lambda v=verts: (v.min(axis=0).tolist(), v.max(axis=0).tolist()))
                safe("  volume matrix", lambda v=vol: v.matrix().tolist())
                # Part type is not documented. Log anything that looks like it.
                for attr in names(vol):
                    if "type" in attr.lower() or "modifier" in attr.lower():
                        safe(f"  volume.{attr}", lambda v=vol, a=attr: _value(getattr(v, a)))
            for ii, inst in enumerate(instances):
                safe(f"object {oi} instance {ii} matrix", lambda i=inst: i.matrix().tolist())
                safe(f"object {oi} instance {ii} left handed", lambda i=inst: i.is_left_handed())
        except Exception as exc:  # noqa: BLE001
            log("object", oi, "FAILED", repr(exc))


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


class ProbeDump(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Nut API probe: dump"

    def on_load(self):
        try:
            log("on_load script capability, thread", thread_name())
            dump_api()
            dump_model("on_load")
        except Exception as exc:  # noqa: BLE001
            log_error("handler", exc)

    def execute(self):
        try:
            log("script execute, thread", thread_name())
            dump_api()
            dump_model("script")
            return orca.ExecutionResult.success("Probe written to the Python log")
        except Exception as exc:  # noqa: BLE001
            log_error("script", exc)
            return orca.ExecutionResult.failure(orca.PluginResult.RecoverableError, str(exc))

    _event_counts = {}

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
            log_error("handler", exc)


PAGE = """<!doctype html><html><body style="font-family:sans-serif;padding:12px">
<h3>Nut API probe</h3><pre id="out"></pre>
<script>
var out = document.getElementById('out');
function say(t) { out.textContent += t + '\\n'; }
function start() {
  if (!window.orca) { say('window.orca missing, retrying'); setTimeout(start, 200); return; }
  var gl = null;
  try { gl = document.createElement('canvas').getContext('webgl'); } catch (e) {}
  window.orca.onMessage(function (m) {
    say('received typeof ' + (typeof m) + ': ' + (typeof m === 'string' ? m : JSON.stringify(m)));
    window.orca.postMessage({type: 'echo', got: typeof m});
  });
  window.orca.postMessage({type: 'ready', webgl: !!gl, agent: navigator.userAgent});
  say('sent ready as an object; webgl=' + (!!gl));
}
start();
</script></body></html>"""


class ProbePage(orca.pages.PagesPluginCapabilityBase):
    def get_name(self):
        return "Nut probe"

    def get_ui(self):
        log("page get_ui, thread", thread_name())
        return PAGE

    def on_message(self, data):
        try:
            log("page on_message type", type(data).__name__, "value", repr(data)[:300],
                "thread", thread_name())
            text = data if isinstance(data, str) else str(dict(data))
            if "ready" in text:
                safe("post_message(dict)", lambda: self.post_message({"type": "as_dict"}))
                safe("post_message(str)", lambda: self.post_message('{"type": "as_string"}'))
        except Exception as exc:  # noqa: BLE001
            log_error("handler", exc)


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
            log_error("handler", exc)

    def execute(self, ctx):
        try:
            step = ctx.step
            first = str(step) not in self._seen
            self._seen.add(str(step))
            log("slicing step", step, "thread", thread_name(), "first" if first else "repeat")
            if first:
                dump_ctx(ctx)
                for key in ("gcode_flavor", "print_sequence", "printable_area", "layer_height"):
                    safe(f"config_value {key}", lambda k=key: repr(ctx.config_value(k)))
                dump_model(f"slicing step {step}")
            if step == orca.slicing.Step.psGCodePostProcess and first:
                log("gcode_path =", repr(ctx.gcode_path))
                if READ_GCODE:
                    self._dump_gcode(ctx)
        except Exception as exc:  # noqa: BLE001
            log_error("handler", exc)
        return orca.ExecutionResult.success()

    def _dump_gcode(self, ctx):
        path = ctx.gcode_path
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
        log("gcode line count =", len(lines))
        for i, line in enumerate(lines[:60]):
            log(f"gcode {i + 1:6d}: {line}")
        markers = ("layer_change", "change_layer", "layer:", "layer_z", "z_height")
        found = [i for i, line in enumerate(lines)
                 if line.startswith(";") and any(m in line.lower() for m in markers)]
        if not found:
            log("no layer-change comment found; showing the first two Z moves instead")
            found = [i for i, line in enumerate(lines)
                     if line.startswith(("G1 Z", "G0 Z"))]
        shown = 0
        last = -100
        for i in found:
            if i - last < 20:
                continue
            last = i
            shown += 1
            log("-- layer change near line", i + 1, "--")
            for j in range(max(0, i - 6), min(len(lines), i + 14)):
                log(f"gcode {j + 1:6d}: {lines[j]}")
            if shown == 2:
                break


@orca.plugin
class NutApiProbe(orca.base):
    def register_capabilities(self):
        orca.register_capability(ProbeDump)
        orca.register_capability(ProbePage)
        orca.register_capability(ProbeSlicing)
