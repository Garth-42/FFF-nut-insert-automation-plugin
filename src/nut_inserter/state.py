"""The cached report and the functions the three capabilities call.

Threads: the check runs on the UI thread (script action, lifecycle events, page
messages). The slice gate and the export step run on Orca's slicing thread and
only read what the UI thread cached here. They never touch the model or the UI.
"""

import json
import time
import traceback

from nutcore import library, pipeline
from nutcore.gcode import inject as gcode_inject
from nutcore.report import ERROR, WARNING, Report

from . import adapter

EVENT_BUDGET = 0.1   # seconds: the longest check allowed inside an event handler

report: Report | None = None   # the last check's report
stale = False                  # the model changed after `report` was made
config_owner = None            # the slicing capability; its settings are the plugin's settings
panel = None                   # the docked panel's handle
tabs: list = []                # Nuts tab capabilities that have said "ready"
last_check_seconds = 0.0
_notified: frozenset = frozenset()
activity: list = []            # recent events as text, shown in the panel for troubleshooting
_steps_seen: set = set()
_edges: tuple = ("", [])       # (snapshot fingerprint, segments)

STALE_MESSAGE = ("E_STALE: the nut report is out of date. Run Check nuts (Plugins window or "
                 "the Nut panel), then slice again.")


def reset() -> None:
    """Forget everything. Used by tests."""
    global report, stale, config_owner, panel, last_check_seconds, _notified, _edges
    report, stale, config_owner, panel = None, False, None, None
    last_check_seconds, _notified, _edges = 0.0, frozenset(), ("", [])
    tabs.clear()
    activity.clear()
    _steps_seen.clear()


def note(text: str) -> None:
    """Remember one line for the panel's activity list.

    Where OrcaSlicer writes a plugin's print() output is not known, so this list
    is the only place a user can see what the slicing steps did. Appending to a
    list is safe from the slicing thread; nothing is posted to the UI here.
    """
    activity.append(f"{time.strftime('%H:%M:%S')}  {text}")
    del activity[:-80]


def note_step(step) -> None:
    """Record the first time each slicing step calls the plugin."""
    name = getattr(step, "name", str(step))
    if name not in _steps_seen:
        _steps_seen.add(name)
        note(f"slicing step {name} reached the plugin")


def guarded(fn, *args):
    """Run fn. On any exception print the traceback and return a failure result."""
    try:
        result = fn(*args)
        return result if result is not None else adapter.success()
    except Exception as exc:  # noqa: BLE001  never crash the host
        traceback.print_exc()
        where = traceback.extract_tb(exc.__traceback__)[-1]
        note(f"ERROR in {getattr(fn, '__name__', fn)}: {exc!r} "
             f"({where.filename.rsplit('/', 1)[-1]} line {where.lineno})")
        return adapter.failure(str(exc))


def set_config_owner(owner) -> None:
    global config_owner
    config_owner = owner


# --- Settings -------------------------------------------------------------------------------

def read_config() -> tuple[dict, str | None]:
    """The saved settings, or the defaults with a message when the saved ones are unusable."""
    if config_owner is None:
        return library.default_config(), None
    try:
        raw = adapter.read_config(config_owner)
        config = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        if not config or "nuts" not in config:
            return library.default_config(), None      # nothing saved yet
        errors = library.validate(config)
        if errors:
            raise library.ConfigError(errors)
        return config, None
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return library.default_config(), f"Saved nut settings are not usable, so the defaults " \
                                         f"are used: {exc}"


# --- The check ------------------------------------------------------------------------------

def run_check():
    """Snapshot the model, detect, cache the report and tell the pages."""
    global report, stale, last_check_seconds
    start = time.perf_counter()
    stale = True                       # stays set if anything below fails
    try:
        config, problem = read_config()
        lib = library.parse(config)
        new = pipeline.detect(adapter.snapshot(), lib)
    except Exception as exc:
        broadcast({"type": "error", "message": f"Nut check failed: {exc}"})
        raise
    last_check_seconds = time.perf_counter() - start
    report, stale = new, False
    broadcast({"type": "report", "report": new.to_dict()})
    if problem:
        broadcast({"type": "error", "message": problem})
    _notify(new)
    s = new.summary
    text = f"{len(new.nuts)} nut(s): {s['ok']} ok, {s['warning']} warning, {s['error']} error"
    note(f"check: {text}, {last_check_seconds * 1000:.0f} ms")
    return adapter.success(text)


def check_action():
    """The Check nuts script action: run the check and bring the panel back if it was closed."""
    result = run_check()
    if panel is not None and not panel.is_open():
        panel.show()
    return result


def model_changed():
    """A model event. Re-check when that is quick, otherwise mark the report stale."""
    if last_check_seconds < EVENT_BUDGET:
        return run_check()
    mark_stale()
    return None


def mark_stale() -> None:
    global stale
    stale = True
    if report is not None:
        report.stale = True
    broadcast({"type": "stale"})


def _notify(new: Report) -> None:
    """One notification when the set of errors and warnings has changed.

    Orca gives a plugin no way to close a notification it raised, so an old one
    stays on screen after the problem is fixed. To make that readable, every
    notification carries the time of its check, and an "all clear" follows once
    nothing is wrong any more.
    """
    global _notified
    problems = [(n, f) for n in new.nuts for f in n.findings if f.level in (ERROR, WARNING)]
    keys = frozenset((n.object, n.instance, n.part, f.code) for n, f in problems)
    fresh = [(n, f) for n, f in problems if (n.object, n.instance, n.part, f.code) not in _notified]
    had_problems = bool(_notified)
    _notified = keys
    stamp = time.strftime("%H:%M:%S")
    if not problems:
        if had_problems:
            adapter.notify_info(f"Nut check {stamp}: all clear, {len(new.nuts)} nut(s) OK. "
                                "Earlier nut messages no longer apply.")
        return
    if not fresh:
        return
    errors = sum(1 for _, f in problems if f.level == ERROR)
    warnings = len(problems) - errors
    text = (f"Nut check {stamp}: {errors} error(s), {warnings} warning(s). "
            f"{fresh[0][1].message}")
    if len(problems) > 1:
        text += " See the Nuts tab for the rest."
    adapter.notify(errors > 0, text)


# --- Slicing thread: the gate and the export step -------------------------------------------

def slice_gate():
    """At posSlice. Cheap and repeatable: it may run once per object."""
    current = report
    if current is None or stale or current.stale:
        note("slice gate: blocked, the report is missing or out of date")
        return adapter.failure(STALE_MESSAGE)
    if not current.nuts:
        return adapter.success()
    failing = [n for n in current.nuts if n.status == "error"]
    config, _ = read_config()
    if failing and config["settings"]["on_error"] == "block":
        shown = []
        for n in failing[:5]:
            shown.append(next(f.message for f in n.findings if f.level == ERROR))
        more = f" (and {len(failing) - 5} more nuts)" if len(failing) > 5 else ""
        note(f"slice gate: blocked by {len(failing)} nut(s) with errors")
        return adapter.failure("Nut check failed. " + " ".join(shown) + more)
    return adapter.success(f"{len(current.nuts)} nut(s) checked")


def export(ctx):
    """At psGCodePostProcess. Edits the G-code file in place, or leaves it untouched."""
    current = report
    if current is None or stale or current.stale:
        note("export: failed, the report is missing or out of date")
        return adapter.failure(STALE_MESSAGE)
    if not current.nuts:
        note("export: no nuts in the report, file left alone")
        return adapter.success()
    config, _ = read_config()
    path = adapter.gcode_path(ctx)
    flavor = adapter.config_value(ctx, "gcode_flavor")
    note(f"export: started on {path!r}, gcode_flavor={flavor!r}")
    with open(path, "rb") as handle:
        text = handle.read().decode("utf-8", "surrogateescape")
    result = gcode_inject.inject(text, current, library.parse(config),
                                 flavor=flavor,
                                 print_sequence=adapter.config_value(ctx, "print_sequence"))
    if result.changed:
        with open(path, "wb") as handle:
            handle.write(result.text.encode("utf-8", "surrogateescape"))
    if result.status != gcode_inject.SKIPPED:
        for old, new in zip(current.nuts, result.report.nuts, strict=True):
            old.export = new.export      # shown the next time a page asks for the report
    print(f"Nut insert: {result.status}: {result.message}")
    note(f"export: {result.status}: {result.message}")
    if result.status == gcode_inject.FAILURE:
        return adapter.failure(result.message)
    if result.status == gcode_inject.SKIPPED:
        return adapter.skipped(result.message)
    return adapter.success(result.message)


# --- Pages ----------------------------------------------------------------------------------

def open_panel(html: str) -> None:
    global panel
    close_panel()                 # the plugin can be loaded twice in one session
    panel = adapter.create_panel(html, on_message=lambda data: guarded(on_panel_message, data),
                                 on_close=lambda *args: None)


def close_panel() -> None:
    global panel
    old, panel = panel, None
    if old is not None:
        try:
            if old.is_open():
                old.close()
        except Exception as exc:  # noqa: BLE001  a panel Orca already removed
            note(f"old panel could not be closed: {exc!r}")


def forget_tab(tab) -> None:
    if tab in tabs:
        tabs.remove(tab)


def broadcast(payload: dict) -> None:
    """Send a message to the panel and to every Nuts tab that is listening.

    A page that has gone away (the plugin was reloaded, a panel was closed) must
    not stop the others from hearing.
    """
    if panel is not None:
        try:
            adapter.post_panel(panel, payload)
        except Exception as exc:  # noqa: BLE001
            note(f"panel did not take a message: {exc!r}")
    for tab in list(tabs):
        try:
            adapter.post_tab(tab, payload)
        except Exception as exc:  # noqa: BLE001
            note(f"a Nuts tab did not take a message and was dropped: {exc!r}")
            forget_tab(tab)


def on_panel_message(data):
    _handle(adapter.decode(data), lambda payload: adapter.post_panel(panel, payload))


def on_tab_message(tab, data):
    if tab not in tabs:
        tabs.append(tab)
    _handle(adapter.decode(data), lambda payload: adapter.post_tab(tab, payload))


def _handle(message: dict, reply) -> None:
    kind = message.get("type")
    try:
        if kind == "ready":
            config, problem = read_config()
            reply({"type": "config", "config": config})
            if report is None and last_check_seconds < EVENT_BUDGET:
                run_check()                       # first page to load: make the first report
            else:
                reply({"type": "report", "report": report.to_dict() if report else None})
                if stale:
                    reply({"type": "stale"})
            if problem:
                reply({"type": "error", "message": problem})
        elif kind == "check":
            run_check()
        elif kind == "save_config":
            _save_config(message.get("config"), reply)
        elif kind == "get_edges":
            reply(_edges_message())
        elif kind == "get_log":
            reply({"type": "log", "lines": list(activity)})
        elif kind == "get_csv":
            reply({"type": "csv", "text": report.to_csv() if report else ""})
        else:
            reply({"type": "error", "message": f"Unknown message type {kind!r}"})
    except Exception as exc:
        reply({"type": "error", "message": str(exc)})
        raise


def _save_config(config, reply) -> None:
    errors = library.validate(config)
    if errors:
        reply({"type": "error", "message": "Not saved. " + " ".join(e + "." for e in errors)})
        return
    if config_owner is None or not adapter.save_config(config_owner, config):
        reply({"type": "error", "message": "Not saved: OrcaSlicer refused the settings."})
        return
    broadcast({"type": "config", "config": config})
    if last_check_seconds < EVENT_BUDGET:
        run_check()                               # new ranges change the findings
    else:
        mark_stale()


def _edges_message() -> dict:
    global _edges
    snap = adapter.snapshot()
    if snap.fingerprint != _edges[0]:
        _edges = (snap.fingerprint, pipeline.preview_edges(snap))
    return {"type": "edges", "segments": _edges[1]}
