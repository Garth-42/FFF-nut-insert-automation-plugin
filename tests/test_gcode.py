"""G-code cases G1 to G11 from docs/SPEC.md."""

import numpy as np
import pytest

from builders import gcode_ring, nut, pocket_block, snapshot
from nutcore import library
from nutcore.gcode.inject import BEGIN, END, inject
from nutcore.gcode.parser import parse
from nutcore.mesh import translation
from nutcore.pipeline import detect

CENTRE = (112.4, 87.25)


def make_report(floor=4.4, centres=(CENTRE,), roof=1.0, config=None, depth=2.0):
    parts = [pocket_block(inner=(5.8, 5.8, depth), floor=floor, roof=roof),
             nut(centre=(0, 0, 0.9))]
    matrices = [translation((x, y, floor)) for x, y in centres]
    return detect(snapshot(parts, matrices), config or library.default_config())


def run(gcode, report=None, firmware="klipper", on_error="block", config=None, **kw):
    config = config or library.default_config()
    config["settings"]["firmware"] = firmware
    config["settings"]["on_error"] = on_error
    return inject(gcode, report or make_report(), library.parse(config), **kw)


def export_codes(result):
    return [f.code for n in result.report.nuts for f in n.findings]


def test_g1_block_follows_last_move_of_last_open_layer():
    gcode = gcode_ring()
    result = run(gcode)
    assert result.status == "success" and result.changed
    lines = result.text.splitlines()
    at = lines.index(f"{BEGIN} layer_z=6.400 count=1")
    assert lines[at + 1] == ("INSERT_NUT KEY=M3SQ CLASS=FLAT X=112.400 Y=87.250 Z=5.300 "
                             "Z_LOW=4.400 YAW=0.00 FEEDER=1 TOOL=0")
    assert lines[at + 2] == END
    assert lines[at + 3] == "G1 Z6.600 F600"          # the next layer starts after the block
    assert lines[at - 1].startswith("G1 X") and " E" in lines[at - 1]
    export = result.report.nuts[0].export
    assert export["layer_z"] == pytest.approx(6.4) and export["z_low"] == pytest.approx(4.4)
    assert export["layer"] == 32
    # Summary sits right after the header block, and nothing else changed.
    assert lines[2] == "; HEADER_BLOCK_END" and lines[3].startswith("; NUT_INSERT_SUMMARY")
    kept = [x for x in lines if not x.startswith((";NUT_INSERT", "INSERT_NUT", "; NUT_INSERT",
                                                  "; nut "))]
    assert kept == gcode.splitlines()


def test_g2_fill_inside_the_pocket():
    gcode = gcode_ring(fill_inside=True)
    result = run(gcode)
    assert result.status == "failure" and result.text == gcode
    assert "E_POCKET_NOT_EMPTY" in export_codes(result)
    assert "Modifier" in result.message and "4.600" in result.message


def test_g3_no_moves_near_the_pocket():
    gcode = gcode_ring(centre=(30.0, 30.0))
    result = run(gcode)
    assert result.status == "success" and not result.changed and result.text == gcode
    assert export_codes(result) == ["N_NOT_ON_PLATE"]


def test_g4_floor_off_the_layer_boundaries_snaps():
    report = make_report(floor=4.45)
    assert report.nuts[0].z_low == pytest.approx(4.45)
    result = run(gcode_ring(floor_z=4.45, roof_z=6.45), report)
    assert result.status == "success"
    export = result.report.nuts[0].export
    assert export["z_low"] == pytest.approx(4.4) and export["z_high"] == pytest.approx(6.2)
    assert export["layer_z"] == pytest.approx(6.4)
    assert "Z=5.300 Z_LOW=4.400" in result.text


def test_g4_printed_depth_loses_the_clearance():
    report = make_report(floor=4.5)                     # half a layer off: 4.5 to 6.5
    assert report.nuts[0].status == "ok"
    result = run(gcode_ring(floor_z=4.55, roof_z=6.45), report)
    assert result.status == "failure"
    assert "E_PRINTED_DEPTH" in export_codes(result)


def test_g5_absolute_and_relative_e_give_the_same_result():
    relative = run(gcode_ring(relative_e=True))
    absolute = run(gcode_ring(relative_e=False))
    assert relative.status == absolute.status == "success"
    assert relative.report.nuts[0].export == absolute.report.nuts[0].export
    assert relative.text.splitlines().index(END) == absolute.text.splitlines().index(END)


def test_g6_arc_through_the_pocket():
    result = run(gcode_ring(arc_inside=True))
    assert result.status == "failure"
    assert "E_POCKET_NOT_EMPTY" in export_codes(result)


def test_g7_reprapfirmware_template():
    result = run(gcode_ring(), firmware="reprapfirmware")
    assert ('M98 P"insert_nut.g" K"M3SQ" C"FLAT" X112.400 Y87.250 Z5.300 L4.400 A0.00 F1 S0'
            in result.text.splitlines())


def test_g7_marlin_template_with_all_placeholders():
    config = library.default_config()
    config["settings"]["templates"]["marlin"] = (
        "; nut {index} {key} {cls}\nG0 X{x} Y{y} F9000\n; place {z} {z_low} {z_high} {yaw} "
        "{feeder} {layer_z}\nG0 X{rx} Y{ry} Z{rz}\nT{tool}")
    result = run(gcode_ring(tool=2), firmware="marlin", config=config)
    lines = result.text.splitlines()
    at = lines.index(f"{BEGIN} layer_z=6.400 count=1")
    assert lines[at + 1:at + 7] == [
        "; nut 1 M3SQ FLAT", "G0 X112.400 Y87.250 F9000",
        "; place 5.300 4.400 6.200 0.00 1 6.400", "G0 X108.900 Y83.750 Z6.400", "T2", END]


def test_g7_auto_firmware_from_flavor():
    assert "INSERT_NUT KEY=M3SQ" in run(gcode_ring(), firmware="auto", flavor="klipper").text
    assert 'M98 P"insert_nut.g"' in run(gcode_ring(), firmware="auto", flavor="reprapfirmware").text
    unknown = run(gcode_ring(), firmware="auto", flavor="smoothie")
    assert unknown.status == "failure" and "E_TEMPLATE" in export_codes(unknown)


def test_g8_empty_marlin_template():
    result = run(gcode_ring(), firmware="marlin")
    assert result.status == "failure"
    assert "E_TEMPLATE" in export_codes(result) and "Marlin needs your own" in result.message


def test_g9_already_processed_file_is_left_alone():
    once = run(gcode_ring()).text
    again = run(once)
    assert again.status == "skipped" and again.text == once and not again.changed


def test_g10_two_nuts_due_at_the_same_layer_share_one_block():
    centres = (CENTRE, (140.0, 87.25))
    result = run(gcode_ring(centre=centres), make_report(centres=centres))
    lines = result.text.splitlines()
    at = lines.index(f"{BEGIN} layer_z=6.400 count=2")
    assert "X=112.400" in lines[at + 1] and "X=140.000" in lines[at + 2]
    assert lines[at + 3] == END
    assert result.text.count(BEGIN) == 1


def test_g11_heights_that_fall_back():
    result = run(gcode_ring(fall_back=True))
    assert result.status == "failure" and "E_PRINT_ORDER" in export_codes(result)


def test_print_sequence_by_object_is_refused():
    result = run(gcode_ring(), print_sequence="by object")
    assert result.status == "failure" and "E_PRINT_ORDER" in export_codes(result)


def test_open_top_pocket_inserts_once_the_nut_is_cleared():
    report = make_report(roof=None)
    result = run(gcode_ring(roof_z=None, top_z=6.4), report)
    assert result.status == "success"
    # Nut top at 6.2, clearance 0.1: the first layer top at or above 6.3 is 6.4.
    assert result.report.nuts[0].export["layer_z"] == pytest.approx(6.4)


def test_on_error_skip_leaves_out_the_failing_nut_with_a_comment():
    centres = (CENTRE, (140.0, 87.25))
    gcode = gcode_ring(centre=centres)
    # Fill only the second pocket.
    extra = "G1 Z5.000\nG0 X139.000 Y87.250\nG1 X141.000 Y87.250 E0.05\n"
    gcode = gcode.replace("G1 Z5.200 F600\n", extra + "G1 Z5.200 F600\n")
    result = run(gcode, make_report(centres=centres), on_error="skip")
    assert result.status == "success" and result.text.count(BEGIN) == 1
    assert "count=1" in result.text
    assert any(line.startswith("; nut 2 NUT_M3SQ skipped: E_POCKET_NOT_EMPTY")
               for line in result.text.splitlines())
    blocked = run(gcode, make_report(centres=centres), on_error="block")
    assert blocked.status == "failure" and blocked.text == gcode


def test_stale_report_fails_the_export():
    report = make_report()
    report.stale = True
    result = run(gcode_ring(), report)
    assert result.status == "failure" and "E_STALE" in result.message


def test_check_error_blocks_the_export():
    report = make_report(depth=1.9)                     # E_DEPTH from the check
    result = run(gcode_ring(roof_z=6.3), report)
    assert result.status == "failure" and "pocket depth" in result.message


def test_line_endings_and_missing_header_are_kept():
    gcode = gcode_ring(newline="\r\n", header=False)
    result = run(gcode)
    assert result.text.startswith("; NUT_INSERT_SUMMARY")
    assert "\r\n" in result.text and "\n" not in result.text.replace("\r\n", "")


def test_parser_tracks_modes_tools_and_arcs():
    text = ("G90\nM82\nT1\nG1 X10 Y0 E1\nG1 X20 E1\nG92 E0\nG1 X30 E0.5\nG91\nG1 X5 Y5\n"
            "G90\nM83\nG3 X40 Y5 I2.5 J0 E0.3\nSET_PRESSURE_ADVANCE ADVANCE=0.02\n"
            "G1 E-1\nM104 S0 T0\n")
    p = parse(text)
    by_line = {int(line): bool(ext) for line, ext in zip(p.seg_line, p.seg_extruding,
                                                         strict=True)}
    assert by_line[3] is True          # E grows
    assert by_line[4] is False         # absolute E unchanged: a travel
    assert by_line[6] is True          # after G92 E0
    assert by_line[8] is False         # relative move, no E
    assert by_line[11] is True         # the arc
    assert np.sum(p.seg_line == 11) >= 8        # half circle of radius 2.5 in 0.5 mm pieces
    assert p.line_pos[8].tolist() == [35.0, 5.0, 0.0]
    assert p.line_tool[0] == -1 and p.line_tool[-1] == 1   # "M104 ... T0" is not a tool change
    assert "".join(p.lines) == text


def test_optional_real_sample_from_orca():
    """When a person has added tests/data/sample.gcode, the parser must find layers in it."""
    from pathlib import Path

    sample = Path(__file__).parent / "data" / "sample.gcode"
    if not sample.exists():
        pytest.skip("tests/data/sample.gcode comes from the probe run in Orca")
    p = parse(sample.read_bytes().decode("utf-8", "surrogateescape"))
    seg, _ = p.extruding
    assert len(np.unique(np.round(seg[:, 5], 3))) > 3
