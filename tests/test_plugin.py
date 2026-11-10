"""Plugin-layer tests, run against the stand-in orca module in tests/fake_orca."""

import json
import types

import orca
import pytest

import nut_inserter
from builders import gcode_ring, nut, pocket_block, snapshot
from nut_inserter import adapter, permissions, state
from nutcore import library
from nutcore.mesh import rotation, translation

EV = orca.LifecycleEvent
OK, FAIL, SKIP = (orca.PluginResult.Success, orca.PluginResult.RecoverableError,
                  orca.PluginResult.Skipped)
BED = translation((112.4, 87.25, 4.4))


def model(inner=(5.8, 5.8, 2.0), matrix=BED):
    return snapshot([pocket_block(inner=inner), nut(centre=(0, 0, 0.9))], [matrix])


@pytest.fixture
def plugin():
    """A freshly loaded plugin: registered, instantiated and on_load called, like Orca does."""
    orca._fake.reset()
    state.reset()
    nut_inserter.NutInserterPlugin().register_capabilities()
    nut_inserter._setup_pending = False
    caps = [cls() for cls in orca._fake.registered]
    for cap in caps:
        cap._saved = '{"activated": true}'      # not the install session
        cap.on_load()
    check, tab, insert = caps
    return types.SimpleNamespace(check=check, tab=tab, insert=insert,
                                 panel=orca._fake.panels[0])


def types_of(messages):
    return [m["type"] for m in messages]


def test_registration_registers_exactly_three_capabilities(plugin):
    assert orca._fake.plugin_classes == [nut_inserter.NutInserterPlugin]
    assert [c.__name__ for c in orca._fake.registered] == ["CheckNuts", "NutsTab", "NutInsert"]
    assert [plugin.check.get_name(), plugin.tab.get_name(), plugin.insert.get_name()] == [
        "Check nuts", "Nuts", "Nut insert"]
    assert state.config_owner is plugin.insert
    assert plugin.insert.get_default_config() == library.default_config()


def test_check_action_reports_the_nut_count(plugin):
    orca._fake.set_model(model())
    result = plugin.check.execute()
    assert result.status == OK and result.message == "1 nut(s): 1 ok, 0 warning, 0 error"
    assert state.report.nuts[0].placement == pytest.approx([112.4, 87.25, 5.3], abs=1e-4)
    assert types_of(plugin.panel.posted) == ["report"]
    assert orca._fake.notifications == []


def test_model_change_event_recomputes_the_report(plugin):
    plugin.check.on_lifecycle_event(EV.ProjectOpened, None)
    assert state.report.nuts == []
    orca._fake.set_model(model())
    plugin.check.on_lifecycle_event(EV.ObjectAdded, None)
    assert len(state.report.nuts) == 1 and not state.stale
    before = state.report
    plugin.check.on_lifecycle_event(EV.SliceCompleted, None)      # not a model event
    assert state.report is before


def test_slow_check_marks_the_report_stale_instead(plugin):
    orca._fake.set_model(model())
    plugin.check.execute()
    before = state.report
    state.last_check_seconds = 0.5                                 # the last check was slow
    plugin.check.on_lifecycle_event(EV.ObjectTransformed, None)
    assert state.report is before and state.stale and before.stale
    assert plugin.panel.posted[-1] == {"type": "stale"}
    assert plugin.insert.execute(orca._fake.Ctx(orca.slicing.Step.posSlice)).status == FAIL
    plugin.check.execute()                                         # a manual check clears it
    assert not state.stale and not state.report.stale


def test_rotating_the_part_raises_one_warning_notification(plugin):
    orca._fake.set_model(model(matrix=BED @ rotation("x", 20)))
    plugin.check.on_lifecycle_event(EV.ObjectTransformed, None)
    assert state.report.nuts[0].cls == "TILTED"
    (level, text), = orca._fake.notifications
    assert level == orca.host.ui.NotificationLevel.WarningNotificationLevel and "tilted" in text
    plugin.check.execute()                                         # same findings: no repeat
    assert len(orca._fake.notifications) == 1
    orca._fake.set_model(model())                                  # problem fixed
    plugin.check.execute()
    level, text = orca._fake.notifications[-1]
    assert level == orca.host.ui.NotificationLevel.RegularNotificationLevel
    assert "all clear" in text and len(orca._fake.notifications) == 2
    plugin.check.execute()                                         # still fine: nothing new
    assert len(orca._fake.notifications) == 2


def test_ready_is_answered_with_config_and_report(plugin):
    orca._fake.set_model(model())
    plugin.panel.on_message({"type": "ready"})
    assert types_of(plugin.panel.posted) == ["config", "report"]
    assert plugin.panel.posted[0]["config"] == library.default_config()
    assert plugin.panel.posted[1]["report"]["summary"] == {"ok": 1, "warning": 0, "error": 0}

    plugin.tab.on_message(json.dumps({"type": "ready"}))           # a JSON string works too
    assert types_of(plugin.tab.posted) == ["config", "report"]
    plugin.tab.on_message({"type": "get_edges"})
    edges = plugin.tab.posted[-1]
    assert edges["type"] == "edges" and 0 < len(edges["segments"]) <= 20000
    assert len(edges["segments"][0]) == 6
    plugin.tab.on_message({"type": "get_csv"})
    assert plugin.tab.posted[-1]["text"].startswith("index,name")


def test_save_config_round_trips(plugin):
    orca._fake.set_model(model())
    plugin.panel.on_message({"type": "ready"})
    config = library.default_config()
    config["nuts"][0]["flat"]["width"] = [5.7, 5.75]              # narrow until the part fails
    plugin.panel.on_message({"type": "save_config", "config": config})
    assert json.loads(plugin.insert.get_config()) == config
    assert types_of(plugin.panel.posted[-2:]) == ["config", "report"]
    finding = state.report.nuts[0].findings[0]
    assert finding.code == "E_WIDTH" and "5.80" in finding.message
    assert state.read_config() == (config, None)


def test_invalid_settings_are_rejected_with_an_error(plugin):
    before = plugin.insert.get_config()
    config = library.default_config()
    config["nuts"][0]["flat"]["width"] = [5.9, 5.7]
    config["settings"]["templates"]["klipper"] = "INSERT_NUT X={nope}"
    plugin.panel.on_message({"type": "save_config", "config": config})
    reply = plugin.panel.posted[-1]
    assert reply["type"] == "error" and "minimum" in reply["message"]
    assert "E_TEMPLATE" in reply["message"]
    assert plugin.insert.get_config() == before


def test_slice_gate(plugin):
    gate = orca._fake.Ctx(orca.slicing.Step.posSlice)
    assert plugin.insert.execute(gate).status == FAIL              # no check has run yet
    plugin.check.execute()
    assert plugin.insert.execute(gate).status == OK                # no nuts
    orca._fake.set_model(model(inner=(6.2, 5.8, 2.0)))
    plugin.check.execute()
    orca._fake.in_slicing_step = True                              # the UI is off limits now
    first, second = plugin.insert.execute(gate), plugin.insert.execute(gate)
    assert first.status == FAIL and "6.20" in first.message
    assert second.message == first.message                         # same answer each time
    orca._fake.in_slicing_step = False

    config = library.default_config()
    config["settings"]["on_error"] = "skip"
    plugin.panel.on_message({"type": "save_config", "config": config})
    assert plugin.insert.execute(gate).status == OK
    other = orca._fake.Ctx(orca.slicing.Step.posPerimeters)
    assert plugin.insert.execute(other).status == OK


def test_export_step_edits_the_gcode_file(plugin, tmp_path):
    orca._fake.set_model(model())
    plugin.check.execute()
    path = tmp_path / "plate_1.gcode"
    original = gcode_ring(newline="\r\n")
    path.write_bytes(original.encode())
    ctx = orca._fake.Ctx(orca.slicing.Step.psGCodePostProcess, gcode_path=str(path),
                         config={"gcode_flavor": "klipper", "print_sequence": "by layer"})
    orca._fake.in_slicing_step = True
    result = plugin.insert.execute(ctx)
    assert result.status == OK, result.message
    text = path.read_bytes().decode()
    assert ";NUT_INSERT_BEGIN layer_z=6.400 count=1\r\nINSERT_NUT KEY=M3SQ CLASS=FLAT" in text
    assert state.report.nuts[0].export["layer_z"] == pytest.approx(6.4)

    again = plugin.insert.execute(ctx)                             # Orca may run the step twice
    assert again.status == SKIP and path.read_bytes().decode() == text


def test_export_fails_when_the_nut_body_still_prints(plugin, tmp_path):
    orca._fake.set_model(model())
    plugin.check.execute()
    path = tmp_path / "plate_1.gcode"
    original = gcode_ring(fill_inside=True)
    path.write_text(original)
    ctx = orca._fake.Ctx(orca.slicing.Step.psGCodePostProcess, gcode_path=str(path),
                         config={"gcode_flavor": "marlin2"})
    result = plugin.insert.execute(ctx)
    assert result.status == FAIL and "NUT_M3SQ" in result.message and "Modifier" in result.message
    assert path.read_text() == original


def test_exceptions_in_entry_points_do_not_propagate(plugin, monkeypatch, capsys):
    def boom():
        raise RuntimeError("model went away")

    monkeypatch.setattr(adapter, "snapshot", boom)
    result = plugin.check.execute()
    assert result.status == FAIL and "model went away" in result.message
    assert plugin.check.on_lifecycle_event(EV.ObjectAdded, None) is None
    assert plugin.tab.on_message({"type": "check"}) is None
    assert plugin.tab.posted[-1]["type"] == "error"
    plugin.panel.on_message("this is not json")
    plugin.panel.on_message({"type": "save_config", "config": None})
    assert plugin.panel.posted[-1]["type"] == "error"
    assert state.stale                                             # a failed check is not trusted
    missing = orca._fake.Ctx(orca.slicing.Step.psGCodePostProcess, gcode_path="/no/such/file")
    assert plugin.insert.execute(missing).status == FAIL
    assert "Traceback" in capsys.readouterr().err


def test_unusable_saved_settings_fall_back_to_defaults(plugin):
    plugin.insert._saved = json.dumps({"schema": 1, "settings": {}, "nuts": []})
    config, problem = state.read_config()
    assert config == library.default_config() and "defaults" in problem
    plugin.panel.on_message({"type": "ready"})
    assert plugin.panel.posted[-1]["type"] == "error"


def test_pages_are_self_contained():
    for html in (nut_inserter.PANEL_HTML, nut_inserter.PREVIEW_HTML):
        assert html.lstrip().startswith("<!doctype html>")
        assert "http://" not in html and "https://" not in html
        assert "<script src" not in html and "<link" not in html
        assert "window.orca.postMessage" in html and "window.orca.onMessage" in html


def test_only_the_plugin_package_imports_orca():
    from pathlib import Path

    core = Path(library.__file__).parent
    for source in core.rglob("*.py"):
        assert "import orca" not in source.read_text(), source


def test_permissions_are_requested_once_at_load():
    (request,) = orca._fake.permission_requests
    assert request["fs_readwrite"] == []
    assert request["fs_read"] == permissions.targets()
    assert all(t.endswith(("/*", ".zip", ".py", ".whl", ".egg")) for t in request["fs_read"])


def test_nut_body_left_as_a_printing_part_blocks_the_slice(plugin):
    from dataclasses import replace

    parts = [pocket_block(), replace(nut(centre=(0, 0, 0.9)), kind="part")]
    orca._fake.set_model(snapshot(parts, [BED]))
    plugin.check.execute()
    assert [f.code for f in state.report.nuts[0].findings] == ["E_NOT_MODIFIER"]
    result = plugin.insert.execute(orca._fake.Ctx(orca.slicing.Step.posSlice))
    assert result.status == FAIL and "Change type, Modifier" in result.message


def test_loading_the_plugin_does_not_import_numpy():
    """Orca prompts per opened file until the permission request is granted, so numpy
    must not be imported while the plugin module loads."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).parent
    paths = [str(root / "fake_orca"), str(root.parent / "src")]
    code = (f"import sys; sys.path[:0] = {paths!r}; import nut_inserter; "
            "nut_inserter.NutInserterPlugin().register_capabilities(); "
            "nut_inserter.NutInsert().get_default_config(); "
            "assert 'numpy' not in sys.modules, 'numpy was imported at load'")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_install_session_only_asks_for_a_restart():
    """In the session the plugin is installed in, the granted permission is not active
    yet, so the plugin must not touch numpy: it says "restart" and does nothing else."""
    orca._fake.reset()
    state.reset()
    nut_inserter._setup_pending = False
    orca._fake.set_model(model())
    check, tab, insert = nut_inserter.CheckNuts(), nut_inserter.NutsTab(), nut_inserter.NutInsert()
    for cap in (check, tab, insert):
        cap.on_load()
    try:
        assert nut_inserter._setup_pending
        assert orca._fake.panels == [] and state.report is None
        assert len(orca._fake.notifications) == 1
        assert "Restart OrcaSlicer" in orca._fake.notifications[0][1]
        assert check.execute().status == FAIL
        assert "Restart OrcaSlicer" in check.execute().message
        check.on_lifecycle_event(EV.ObjectAdded, None)
        tab.on_message({"type": "ready"})
        assert tab.posted == [{"type": "error", "message": permissions.RESTART_NOTICE}]
        assert insert.execute(orca._fake.Ctx(orca.slicing.Step.posSlice)).status == FAIL
        assert state.report is None
        # The next session: every capability has a stored config now.
        nut_inserter._setup_pending = False
        for cap in (check, tab, insert):
            cap.on_load()
        assert not nut_inserter._setup_pending and len(orca._fake.panels) == 1
        assert check.execute().status == OK
    finally:
        nut_inserter._setup_pending = False


def test_activity_list_records_slicing_and_export(plugin, tmp_path):
    orca._fake.set_model(model())
    plugin.check.execute()
    path = tmp_path / "plate_1.gcode"
    path.write_text(gcode_ring())
    plugin.insert.execute(orca._fake.Ctx(orca.slicing.Step.posSlice))
    plugin.insert.execute(orca._fake.Ctx(orca.slicing.Step.posSlice))
    plugin.insert.execute(orca._fake.Ctx(orca.slicing.Step.psGCodePostProcess,
                                         gcode_path=str(path), config={"gcode_flavor": "klipper"}))
    plugin.insert.execute(orca._fake.Ctx(orca.slicing.Step.psGCodePostProcess,
                                         gcode_path="/no/such/file"))
    plugin.panel.on_message({"type": "get_log"})
    lines = plugin.panel.posted[-1]["lines"]
    text = "\n".join(lines)
    assert sum("slicing step posSlice reached" in line for line in lines) == 1
    assert "check: 1 nut(s): 1 ok" in text
    assert "export: started on" in text and "gcode_flavor='klipper'" in text
    assert "export: success: 1 nut insert block(s) written." in text
    assert "ERROR in export: FileNotFoundError" in text


def test_plugin_survives_being_loaded_again(plugin):
    """OrcaSlicer loaded the plugin module a second time when it was switched on for a
    process preset. The new module object had no "state" attribute, and every call failed
    with "cannot import name 'state' from 'nut_inserter'"."""
    orca._fake.set_model(model())
    plugin.check.execute()
    first_report, first_panel = state.report, plugin.panel
    plugin.tab.on_message({"type": "ready"})

    del nut_inserter.state                       # what a second load leaves behind
    plugin.check.on_unload()
    plugin.tab.on_unload()
    assert not first_panel.is_open() and state.tabs == []
    check, tab, insert = nut_inserter.CheckNuts(), nut_inserter.NutsTab(), nut_inserter.NutInsert()
    for cap in (check, tab, insert):
        cap._saved = '{"activated": true}'
        cap.on_load()

    assert state.report is first_report          # the cached report was kept
    assert len(orca._fake.panels) == 2 and orca._fake.panels[1].is_open()
    assert state.config_owner is insert
    assert insert.execute(orca._fake.Ctx(orca.slicing.Step.posSlice)).status == OK
    tab.on_message({"type": "ready"})
    assert types_of(tab.posted) == ["config", "report"]
    assert check.execute().status == OK


def test_a_dead_page_does_not_stop_the_others(plugin):
    orca._fake.set_model(model())
    plugin.tab.on_message({"type": "ready"})

    def gone(payload):
        raise RuntimeError("page was destroyed")

    plugin.tab.post_message = gone
    assert plugin.check.execute().status == OK
    assert plugin.panel.posted[-1]["type"] == "report" and state.tabs == []
