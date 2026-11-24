"""The cached report and the functions the three capabilities call.

Threads: the check runs on the UI thread (script action, lifecycle events, page
messages). The slice gate and the export step run on Orca's slicing thread and
only read what the UI thread cached here. They never touch the model or the UI.
"""

import json
import threading
import time
import traceback

import nutcore
from heatsetcore import export as heatset_export
from heatsetcore import place as heatset_place
from heatsetcore import profile as heatset_profile
from heatsetcore import routine as heatset_routine
from heatsetcore.detect import detect_inserts
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
# (is_error, text) from the last export, for the UI thread to show once. The export runs on
# the slicing thread, where a notification could deadlock.
pending_export_warning: tuple | None = None
# (degrees, where from) the last export used for heat-set inserts, for the Heat-set tab.
last_insert_temperature: tuple | None = None

STALE_MESSAGE = ("E_STALE: the nut report is out of date. Run Check nuts (Plugins window or "
                 "the Nut panel), then slice again.")


def reset() -> None:
    """Forget everything. Used by tests."""
    global report, stale, config_owner, panel, last_check_seconds, _notified, _edges
    global pending_export_warning, last_insert_temperature
    report, stale, config_owner, panel = None, False, None, None
    last_check_seconds, _notified, _edges = 0.0, frozenset(), ("", [])
    pending_export_warning = last_insert_temperature = None
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
        config = library.migrate(config)               # keeps a schema-1 nut library
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
    """Snapshot the model, find nuts and heat-set inserts, cache the report, tell the pages."""
    global report, stale, last_check_seconds
    show_export_warning()
    start = time.perf_counter()
    stale = True                       # stays set if anything below fails
    try:
        config, problem = read_config()
        lib = library.parse(config)
        snap = adapter.snapshot()
        new = pipeline.detect(snap, lib)
        new.nuts += detect_inserts(snap, lib, first_index=len(new.nuts) + 1)
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
    text = f"{_what(new)}: {s['ok']} ok, {s['warning']} warning, {s['error']} error"
    note(f"check: {text}, {last_check_seconds * 1000:.0f} ms")
    return adapter.success(text)


def _what(current: Report) -> str:
    """'2 nut(s)', or '2 nut(s), 3 heat-set insert(s)' when there are inserts."""
    inserts = sum(1 for n in current.nuts if n.kind == "heatset")
    text = f"{len(current.nuts) - inserts} nut(s)"
    return text + (f", {inserts} heat-set insert(s)" if inserts else "")


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
            adapter.notify_info(f"Nut check {stamp}: all clear, {_what(new)} OK. "
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
        reasons: list[str] = []
        for n in failing:
            reason = _reason(n, next(f for f in n.findings if f.level == ERROR))
            if reason not in reasons:
                reasons.append(reason)
        more = f" (and {len(reasons) - 5} more)" if len(reasons) > 5 else ""
        note(f"slice gate: blocked by {len(failing)} item(s) with errors")
        return adapter.failure("Nut check failed. " + " ".join(reasons[:5]) + more)
    return adapter.success(f"{_what(current)} checked")


def _reason(record, problem) -> str:
    """A finding's message for the gate. A profile problem is the same for every insert of
    that profile, so it is shown once, without the insert's label."""
    prefix = record.label + ": "
    if problem.code == "E_PROFILE" and problem.message.startswith(prefix):
        return problem.message[len(prefix):]
    return problem.message


def export(ctx):
    """At psGCodePostProcess. Edits the G-code file in place, or leaves it untouched.

    Nut blocks first (nutcore.gcode.inject), then the heat-set header, preheats and blocks
    on that output (heatsetcore.export). Either refusing leaves the file as Orca wrote it.
    """
    global last_insert_temperature
    current = report
    if current is None or stale or current.stale:
        note("export: failed, the report is missing or out of date")
        _warn_after_export(True, "refused. " + STALE_MESSAGE)
        return adapter.failure(STALE_MESSAGE)
    if not current.nuts:
        note("export: no nuts or inserts in the report, file left alone")
        return adapter.success()
    config, _ = read_config()
    lib = library.parse(config)
    path = adapter.gcode_path(ctx)
    flavor = adapter.config_value(ctx, "gcode_flavor")
    note(f"export: started on {path!r}, gcode_flavor={flavor!r}")
    with open(path, "rb") as handle:
        text = handle.read().decode("utf-8", "surrogateescape")
    nuts = gcode_inject.inject(text, current, lib, flavor=flavor,
                               print_sequence=adapter.config_value(ctx, "print_sequence"))
    print(f"Nut insert: {nuts.status}: {nuts.message}")
    note(f"export: nuts: {nuts.status}: {nuts.message}")
    if nuts.status == gcode_inject.FAILURE:
        _warn_after_export(True, "refused. " + nuts.message)
        return adapter.failure(nuts.message)

    has_inserts = any(n.kind == "heatset" for n in current.nuts)
    heat = heatset_export.export(nuts.text, current.nuts, lib, version=nutcore.__version__,
                                 filament_type=_first_filament(
                                     adapter.config_value(ctx, "filament_type")),
                                 flavor=flavor)
    if has_inserts:
        info = heatset_export.export_info(heat)
        for n in current.nuts:
            if n.kind == "heatset" and n.label in info:
                n.export = info[n.label]
        if heat.temperature is not None:
            last_insert_temperature = (heat.temperature, heat.temperature_source)
        print(f"Nut insert: heat-set: {heat.status}: {heat.message}")
        note(f"export: heat-set: {heat.status}: {heat.message}")
    if heat.status == heatset_place.FAILURE:
        _warn_after_export(True, "refused. " + heat.message)
        return adapter.failure(heat.message)

    if nuts.status != gcode_inject.SKIPPED:     # only now is the nut half sure to be written
        for old, new in zip(current.nuts, nuts.report.nuts, strict=True):
            if old.kind == "nut":
                old.export = new.export  # shown the next time a page asks for the report
    if nuts.changed or heat.changed:
        with open(path, "wb") as handle:
            handle.write(heat.text.encode("utf-8", "surrogateescape"))
    left_out = nuts.left_out + heat.left_out
    if left_out:
        _warn_after_export(False, _left_out_text(left_out))
    has_nuts = any(n.kind == "nut" for n in current.nuts)
    message = " ".join(part for part, used in ((nuts.message, has_nuts),
                                                (heat.message, has_inserts)) if used)
    skipped = nuts.status == gcode_inject.SKIPPED or heat.status == heatset_place.SKIPPED
    if skipped and not (nuts.changed or heat.changed):
        return adapter.skipped(message)
    return adapter.success(message)


def _first_filament(value) -> str | None:
    """The first extruder's filament type from Orca's setting, "PLA;PETG" or "PLA"."""
    if not value:
        return None
    first = str(value).replace(",", ";").split(";")[0].strip().strip('"')
    return first or None


def _warn_after_export(is_error: bool, text: str) -> None:
    """Keep a warning for the UI thread to show once the export has finished."""
    global pending_export_warning
    pending_export_warning = (is_error, f"Nut insert export {time.strftime('%H:%M:%S')}: {text}")
    note(f"export: a warning waits for the export to finish: {text}")


def _left_out_text(left_out) -> str:
    names = "; ".join(f"{label} ({code})" for label, code, _ in left_out[:5])
    more = f" and {len(left_out) - 5} more" if len(left_out) > 5 else ""
    return (f"{len(left_out)} item(s) left out because of errors: {names}{more}. Each is named "
            "in a comment at the top of the G-code, and the Nuts tab shows the fix.")


def show_export_warning() -> None:
    """Show the last export's warning as a notification, once.

    Only on Orca's main thread: the export itself runs on the slicing thread, where a
    notification could deadlock, and a script's execute runs on a background thread.
    """
    global pending_export_warning
    if pending_export_warning is None:
        return
    if threading.current_thread() is not threading.main_thread():
        return
    (is_error, text), pending_export_warning = pending_export_warning, None
    adapter.notify(is_error, text)
    broadcast({"type": "error", "message": text})


def export_finished():
    """Orca's GCodeExportFinished event: the export is over, so show what it left out."""
    show_export_warning()


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
    show_export_warning()          # an export may have finished since the last message
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
            if last_insert_temperature is not None:
                reply(_insert_temperature_message())
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
        elif kind == "check_profile":
            reply(_profile_check(message.get("profile")))
        else:
            reply({"type": "error", "message": f"Unknown message type {kind!r}"})
    except Exception as exc:
        reply({"type": "error", "message": str(exc)})
        raise


def _save_config(config, reply) -> None:
    config = library.migrate(config)      # a library exported before schema 2 still imports
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


def _profile_check(prof) -> dict:
    """What the Heat-set and Machine settings tabs show beside a profile being edited: the
    broken rules, named, and the derived values once the profile is sound."""
    problems = heatset_profile.validate_profile(prof)
    derived = None if problems else heatset_routine.derived(prof)
    return {"type": "profile_check", "problems": problems, "derived": derived}


def _insert_temperature_message() -> dict:
    temp, source = last_insert_temperature
    return {"type": "insert_temp", "value": temp, "source": source}


def _edges_message() -> dict:
    global _edges
    snap = adapter.snapshot()
    if snap.fingerprint != _edges[0]:
        _edges = (snap.fingerprint, pipeline.preview_edges(snap))
    return {"type": "edges", "segments": _edges[1]}
