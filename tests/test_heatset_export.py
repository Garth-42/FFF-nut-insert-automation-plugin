"""The heat-set half of the export step (heatsetcore.export): detection records to G-code.

The model is hole_block's Ø4 x 6.7 hole under gcode_ring's pocket, which is open from
Z 3.2 to the top at Z 10.0, so the empty-hole proof passes and the insert's top, Z 10.0,
is the last layer.
"""

import pytest

from builders import gcode_ring, hole_block, insert_body, nut, pocket_block, snapshot
from heatsetcore import export
from heatsetcore.detect import detect_inserts
from nutcore import library
from nutcore.gcode.inject import inject
from nutcore.mesh import rotation, translation
from nutcore.pipeline import detect
from nutcore.report import Report

CENTRE = (112.4, 87.25)
BED = translation((*CENTRE, 0.0))
FLUSH = (0.0, 0.0, 10.0 - 2.85)


def config(on_error="block", **change) -> dict:
    out = library.default_config()
    out["settings"]["on_error"] = on_error
    out["heatset"]["profiles"][0].update({"tbd": [], **change})
    return out


def records(parts=None, matrices=None, cfg=None):
    parts = parts or [hole_block(), insert_body(centre=FLUSH)]
    return detect_inserts(snapshot(parts, matrices or [BED]), library.parse(cfg or config()))


def gcode(temp=210) -> str:
    text = gcode_ring(centre=CENTRE, floor_z=3.2, roof_z=None, top_z=10.0)
    return text.replace("G28\n", f"G28\nM104 S{temp}\n") if temp else text


def run(found, cfg=None, text=None, **kw):
    return export.export(text or gcode(), found, library.parse(cfg or config()),
                         version="0.3.0", **kw)


def test_an_insert_from_detection_gets_its_header_and_block():
    found = records()
    result = run(found)
    assert result.status == "success", result.message
    assert result.message == "1 heat-set insert(s) in 1 block(s)."
    out = result.text.splitlines()
    assert '; HEATSET profile "Concept D" heatsetcore 0.3.0' in out
    assert "; insert_temp_used = 225 (print temperature 210 C + 15 C)" in out
    assert (result.temperature, result.temperature_source) == (
        225.0, "print temperature 210 °C + 15 °C")
    begin = out.index('M98 P"heatset/begin.g" K"M3x5.7" S225 Z15.000 C1')
    assert out[begin + 2] == 'M98 P"heatset/insert_start.g" I1 O"" X112.400 Y87.250 Z10.000'
    assert export.export_info(result) == {
        "HEATSET_M3x5.7 #1": {"block": 1, "z_top": 10.0, "object": "",
                              "after_line": result.inserts[0].line + 1}}


def test_an_insert_its_checks_refused_is_left_out_or_blocks():
    found = records([hole_block(depth=6.5), insert_body(centre=FLUSH)])
    assert found[0].findings[0].code == "E_DEPTH"
    blocked = run(found)
    assert blocked.status == "failure" and blocked.text == gcode()
    assert blocked.message.startswith("Heat-set inserts: HEATSET_M3x5.7 #1: hole depth 6.50")
    skipped = run(found, config(on_error="skip"))
    assert skipped.status == "success" and skipped.changed
    out = skipped.text.splitlines()
    assert ("; HEATSET skipped HEATSET_M3x5.7 #1: E_DEPTH hole depth 6.50 mm, allowed 6.70 mm "
            "or more. Increase by at least 0.20 mm in CAD and re-export.") in out
    assert not any("heatset/begin.g" in x for x in out)
    assert [code for _, code, _ in skipped.left_out] == ["E_DEPTH"]
    assert export.export_info(skipped) == {"HEATSET_M3x5.7 #1": {"skipped": "E_DEPTH"}}


def test_a_tilted_insert_is_named_for_fitting_by_hand():
    found = records(matrices=[BED @ rotation("x", 20)])
    result = run(found)
    assert result.status == "success" and result.left_out == []
    assert result.message == "0 heat-set insert(s) in 0 block(s), 1 to fit by hand."
    comment = next(x for x in result.text.splitlines() if x.startswith("; HEATSET by hand"))
    assert comment.startswith("; HEATSET by hand HEATSET_M3x5.7 #1: W_TILTED the insert's axis "
                              "is tilted 20.0 deg from vertical")


def test_without_a_print_temperature_the_filament_table_is_used():
    result = run(records(), text=gcode(temp=None), filament_type="PETG")
    assert result.temperature == 245.0
    unknown = run(records(), text=gcode(temp=None), filament_type="TPU")
    assert unknown.status == "failure" and "no insert temperature" in unknown.message


def test_the_unmeasured_default_profile_refuses_the_export():
    fresh = library.default_config()
    found = records(cfg=fresh)
    result = run(found, cfg=fresh)
    assert result.status == "failure" and "rule 5" in result.message


def test_nothing_to_do_without_inserts_and_a_second_run_is_skipped():
    assert run([]).status == "success" and run([]).text == gcode()
    first = run(records())
    again = run(records(), text=first.text)
    assert again.status == "skipped" and again.text == first.text


def test_nut_and_insert_records_each_go_to_their_own_step():
    """One report with a nut and an insert: inject writes the nut, export the insert."""
    nut_model = snapshot([pocket_block(), nut(centre=(0, 0, 0.9))],
                         [translation((60.0, 40.0, 4.4))])
    report = detect(nut_model, config())
    report.nuts += records()
    report.nuts[1].index = 2
    nuts_only = inject(gcode(), Report(nuts=[report.nuts[1]]), library.parse(config()))
    assert nuts_only.message == "No nuts in the report." and not nuts_only.changed
    result = run(report.nuts)
    assert result.status == "success" and len(result.inserts) == 1
    assert result.inserts[0].spec.label == "HEATSET_M3x5.7 #2"


@pytest.mark.parametrize("on_error", ["block", "skip"])
def test_a_second_profile_in_one_print_is_refused(on_error):
    """detect_inserts refuses it already; the export does not rely on that."""
    cfg = config(on_error=on_error)
    second = {**cfg["heatset"]["profiles"][0], "name": "M4 tool", "insert_key": "M4x8"}
    cfg["heatset"]["profiles"].append(second)
    found = records(cfg=cfg) + records(
        [hole_block(), insert_body(centre=FLUSH, name="HEATSET_M4x8")], cfg=cfg)
    found[1].index = 2
    assert [r.findings for r in found] == [[], []]          # separate snapshots
    result = run(found, cfg)
    if on_error == "block":
        assert result.status == "failure" and "one heat-set tool per print" in result.message
    else:
        assert result.status == "success" and result.left_out[0][:2] == (
            "HEATSET_M4x8 #2", "E_PROFILE")


@pytest.mark.parametrize(("firmware", "flavor", "ok"), [
    ("reprapfirmware", "reprapfirmware", True), ("klipper", "klipper", True),
    ("reprapfirmware", "klipper", False), ("klipper", "marlin2", False),
    ("reprapfirmware", None, True)])
def test_the_profile_firmware_must_match_the_gcode_flavor(firmware, flavor, ok):
    cfg = config(firmware=firmware)
    result = run(records(cfg=cfg), cfg, flavor=flavor)
    assert (result.status == "success") == ok, result.message
    if not ok:
        assert "flavor is " + flavor in result.message and "Machine settings" in result.message
        assert result.text == gcode()


def test_a_klipper_export_writes_klipper_lines():
    cfg = config(firmware="klipper")
    result = run(records(cfg=cfg), cfg, flavor="klipper")
    out = result.text.splitlines()
    assert "HEATSET_REQUIRE KEY=M3x5.7 COUNT=1 TEMP=225" in out
    assert "HEATSET_INSERT_START INDEX=1 OBJECT= X=112.400 Y=87.250 Z_TOP=10.000" in out
    assert not any(x.startswith("M98 ") for x in out)
