"""Heat-set placement (heatsetcore.place): the plan's cases P1-P13, P15 and P16.

On the real export (Orca 2.5.0, Klipper flavour) and its RepRapFirmware variant, made by
dropping the EXCLUDE_OBJECT lines so the comment labels RRF reads are the only ones. The
sample's nut pocket, open from Z 1.0 to 3.0, stands in for a hole. Inserts are made by
hand until detection exists (milestone 5).
"""

import difflib
import re
from pathlib import Path

import pytest

from builders import gcode_ring, sample_record
from heatsetcore import place, profile
from nutcore import library
from nutcore.gcode.inject import inject
from nutcore.gcode.parser import parse
from nutcore.report import Report

SAMPLE = Path(__file__).parent / "data" / "sample.gcode"
POCKET = {"x": 164.706, "y": 158.320}
OBJECT = "Configuration 1.step id:0 copy 0"
WIPE = "G1 X112.068 Y125.165 E-.19947"          # the end of the layer at Z 3.0
CENTRE = (112.4, 87.25)                           # gcode_ring's pocket


def sample_text(rrf=True) -> str:
    lines = SAMPLE.read_bytes().decode("utf-8", "surrogateescape").splitlines(keepends=True)
    return "".join(x for x in lines if not (rrf and x.startswith("EXCLUDE_OBJECT")))


def measured(**change) -> dict:
    """The default profile with every TBD measured (placeholders kept)."""
    p = profile.default_profile()
    p["tbd"] = []
    p.update(change)
    assert profile.validate_profile(p) == []
    return p


def insert(label="HEATSET_M3x5.7 #1", **spec) -> place.InsertSpec:
    values = {"z_top": 3.0, "hole_d": 4.0, "bottom_z": 1.0, **POCKET, **spec}
    return place.InsertSpec(label=label, **values)


def ring_insert(x, y, label="HEATSET_M3x5.7 #1", z_top=6.0) -> place.InsertSpec:
    return place.InsertSpec(label, x, y, z_top=z_top, hole_d=4.0, bottom_z=4.4)


def lines(result) -> list[str]:
    return result.text.splitlines()


def test_p1_after_layer_on_the_rrf_variant():
    result = place.place(sample_text(), [insert()], measured(), version="0.2.6")
    assert result.status == "success", result.message
    out = lines(result)
    head = out.index('; HEATSET profile "Concept D" heatsetcore 0.2.6')
    first_label = next(i for i, x in enumerate(out) if x.startswith("; printing object"))
    assert head < first_label
    assert out[first_label - 1] == 'M98 P"heatset/require.g" K"M3x5.7" C1 S235'
    begin = out.index('M98 P"heatset/begin.g" K"M3x5.7" S235 Z8.000 C1')
    assert out[begin - 1] == "; HEATSET block 1: after_layer, inserts=1, key M3x5.7"
    assert out[begin - 2] == WIPE                  # after the layer's retract and wipe
    assert out[begin + 2] == (f'M98 P"heatset/insert_start.g" I1 O"{OBJECT}" X164.706 '
                              "Y158.320 Z3.000")
    (planned,) = result.inserts
    assert (planned.z_top, planned.block, planned.object) == (3.0, 1, OBJECT)
    kept = [x for x in out if not x.startswith(("; HEATSET", "; insert", "M98 ", "G90", "G0 ",
                                                 "; "))]
    original = [x for x in sample_text().splitlines() if not x.startswith(("G90", "; "))]
    assert [x for x in kept if x] == [x for x in original if x]       # nothing else changed


def test_p1_klipper_labels_and_names():
    result = place.place(sample_text(rrf=False), [insert()], measured())
    out = lines(result)
    begin = next(i for i, x in enumerate(out) if "heatset/begin.g" in x)
    assert out[begin - 2] == "EXCLUDE_OBJECT_END NAME=Configuration_1.step_id_0_copy_0"
    assert 'O"Configuration_1.step_id_0_copy_0"' in out[begin + 2]


def test_p2_end_of_print_goes_before_the_end_gcode():
    top = insert(x=150.0, y=150.0, z_top=12.2, bottom_z=12.2)      # on the part's top face
    result = place.place(sample_text(), [top], measured(timing="end_of_print"))
    assert result.status == "success", result.message
    out = lines(result)
    end = out.index('M98 P"heatset/end.g"')
    assert out.index("M98 P\"heatset/begin.g\" K\"M3x5.7\" S235 Z17.200 C1") < end
    assert out.index("PRINT_END") > end
    assert out[out.index("; HEATSET block 1: end_of_print, inserts=1, key M3x5.7") - 1] == (
        "G1 X109.979 Y175.005 E-.24")             # the last wipe


def _r_before(out, index):
    return [float(m[1]) for x in out[:index] if (m := re.match(r"M73 P\d+ R(\d+)", x))]


def test_p3_preheat_by_the_time_estimates():
    out = lines(place.place(sample_text(), [insert()], measured()))
    heat = out.index('M98 P"heatset/preheat.g" S235')
    begin = next(i for i, x in enumerate(out) if "heatset/begin.g" in x)
    r_block = _r_before(out, begin)[-1]
    assert out[heat - 1].startswith("M73") and _r_before(out, heat)[-1] >= r_block + 2
    later = [r for r in _r_before(out, begin)[len(_r_before(out, heat)):]]
    assert later and all(r < r_block + 2 for r in later)       # the last line early enough


def test_p4_preheat_by_layers_without_estimates():
    text = "".join(x for x in sample_text().splitlines(keepends=True)
                   if not x.startswith("M73"))
    out = place.place(text, [insert()], measured(preheat_layers=2)).text
    parsed = parse(out)
    heat = next(i for i, x in enumerate(parsed.lines) if "heatset/preheat.g" in x)
    assert parsed.line_pos[heat - 1][2] == pytest.approx(2.6)  # two layers below 3.0


def test_p5_no_labels_block_before_the_next_layer():
    text = gcode_ring(roof_z=None, top_z=7.4)
    result = place.place(text, [ring_insert(*CENTRE)], measured(insert_temp=230.0))
    assert result.status == "success", result.message
    out = lines(result)
    end = out.index('M98 P"heatset/end.g"')
    assert out[end + 1] == "G1 Z6.200 F600"
    assert out.index('; HEATSET profile "Concept D" heatsetcore ') < out.index("G1 Z0.200 F600")


def test_p7_plastic_in_the_hole_stops_the_insert():
    text = gcode_ring(roof_z=None, top_z=7.4, fill_inside=True)
    result = place.place(text, [ring_insert(*CENTRE)], measured(insert_temp=230.0))
    assert result.status == "failure" and result.text == text
    assert result.left_out[0][1] == "E_POCKET_NOT_EMPTY"
    clean = place.place(gcode_ring(roof_z=None, top_z=7.4), [ring_insert(*CENTRE)],
                        measured(insert_temp=230.0))
    assert clean.status == "success"                # the hole's own perimeter is not plastic in it


def test_p8_keep_out_at_the_end_of_the_print():
    """A ring 20 mm away in +X, where the pad sits during the push, rises above the surface."""
    text = gcode_ring(centre=[CENTRE, (CENTRE[0] + 20, CENTRE[1])], roof_z=None, top_z=7.4)
    hole = ring_insert(*CENTRE)
    late = place.place(text, [hole], measured(insert_temp=230.0, timing="end_of_print"))
    assert late.status == "failure" and late.left_out[0][1] == "E_KEEP_OUT"
    assert "the pad, beside the hole during the hot push" in late.message
    early = place.place(text, [hole], measured(insert_temp=230.0))     # after_layer
    assert early.status == "success", early.message


def test_p9_inserts_on_one_layer_share_a_block_nearest_first():
    centres = [(100.0, 80.0), (150.0, 80.0), (120.0, 80.0)]   # printed in this order
    text = gcode_ring(centre=centres, roof_z=None, top_z=7.4)
    holes = [ring_insert(x, y, f"HEATSET_M3x5.7 #{i}") for i, (x, y) in enumerate(centres, 1)]
    result = place.place(text, holes, measured(insert_temp=230.0))
    out = lines(result)
    assert sum(x.startswith("; HEATSET block") for x in out) == 1
    order = [x.split()[3] for x in out if x.startswith("; insert ")]
    assert order == ["X120.000", "X100.000", "X150.000"]     # from the toolhead, at the last


def test_p10_a_nut_block_at_the_same_point_comes_first():
    config = library.default_config()
    config["settings"]["firmware"] = "reprapfirmware"
    nuts = inject(sample_text(), Report(nuts=[sample_record()]), library.parse(config))
    out = lines(place.place(nuts.text, [insert()], measured()))
    assert out.index(";NUT_INSERT_END") < out.index(
        "; HEATSET block 1: after_layer, inserts=1, key M3x5.7")
    assert out[out.index(";NUT_INSERT_END") + 1].startswith("; HEATSET block 1")


@pytest.mark.parametrize(("change", "filament", "expected"), [
    (None, None, "S235"),                                     # M109 S220 + 15
    (("M109 S220", "G10 P0 S220 R200"), None, "S235"),        # RepRapFirmware style
    (("M109 S220", "M140 S55"), "PETG", "S245"),              # none in the file: the table
])
def test_p11_insert_temperature(change, filament, expected):
    text = sample_text() if change is None else sample_text().replace(*change)
    result = place.place(text, [insert()], measured(), filament_type=filament)
    assert f'M98 P"heatset/preheat.g" {expected}' in lines(result)
    manual = place.place(text, [insert()], measured(insert_temp=228.0))
    assert 'M98 P"heatset/preheat.g" S228' in lines(manual)


def test_p11_no_temperature_anywhere_refuses():
    text = sample_text().replace("M109 S220", "M140 S55")
    result = place.place(text, [insert()], measured(), filament_type="TPU")
    assert result.status == "failure" and result.left_out[0][1] == "E_PROFILE"
    assert "no insert temperature" in result.message


def test_p12_a_processed_file_is_left_alone():
    once = place.place(sample_text(), [insert()], measured()).text
    again = place.place(once, [insert()], measured())
    assert again.status == "skipped" and again.text == once and not again.changed


def test_p15_magazine_capacity():
    centres = [(100.0, 80.0), (150.0, 80.0), (120.0, 80.0)]
    text = gcode_ring(centre=centres, roof_z=None, top_z=7.4)
    holes = [ring_insert(x, y, f"HEATSET_M3x5.7 #{i}") for i, (x, y) in enumerate(centres, 1)]
    blocked = place.place(text, holes, measured(insert_temp=230.0, magazine_capacity=2))
    assert blocked.status == "failure" and "rule 9" in blocked.message
    skipped = place.place(text, holes, measured(insert_temp=230.0, magazine_capacity=2),
                          on_error="skip")
    out = lines(skipped)
    assert skipped.status == "success" and sum(x.startswith("; insert ") for x in out) == 2
    assert [label for label, code, _ in skipped.left_out] == ["HEATSET_M3x5.7 #2"]  # done last
    assert any(x.startswith("; HEATSET skipped HEATSET_M3x5.7 #2: E_MAGAZINE") for x in out)


def test_p16_skip_leaves_a_failing_insert_out_with_a_comment():
    text = gcode_ring(roof_z=None, top_z=7.4)
    good = ring_insert(*CENTRE)
    on_the_wall = ring_insert(CENTRE[0] + 3.5, CENTRE[1], "HEATSET_M3x5.7 #2")
    result = place.place(text, [good, on_the_wall], measured(insert_temp=230.0),
                         on_error="skip")
    assert result.status == "success" and result.changed
    assert result.left_out == [(on_the_wall.label, "E_POCKET_NOT_EMPTY",
                                result.left_out[0][2])]
    out = lines(result)
    assert sum(x.startswith("; insert ") for x in out) == 1
    assert any(x.startswith("; HEATSET skipped HEATSET_M3x5.7 #2: E_POCKET_NOT_EMPTY")
               for x in out)


def test_rule_5_tbds_refuse_a_normal_export_but_not_a_rehearsal():
    p = profile.default_profile()                             # every TBD still open
    result = place.place(sample_text(), [insert()], p)
    assert result.status == "failure" and "rule 5" in result.message
    rehearse = place.place(sample_text(), [insert()], dict(p, mode="rehearse"))
    assert rehearse.status == "success" and 'B"rehearse"' in rehearse.text


def test_an_insert_with_nothing_printed_around_it_is_skipped_quietly():
    far = insert(x=20.0, y=20.0)
    result = place.place(sample_text(), [far], measured())
    assert result.status == "success" and not result.changed
    assert result.inserts[0].findings[0].code == "N_NOT_ON_PLATE"


# --- P14: the Klipper template set at the same positions ------------------------------------

def insertion_points(original: str, result: str) -> list[tuple[int, int]]:
    """(original line index, lines added there) for each place the result adds lines; it
    must change nothing else."""
    ops = difflib.SequenceMatcher(a=original.splitlines(), b=result.splitlines(),
                                  autojunk=False).get_opcodes()
    assert all(tag in ("equal", "insert") for tag, *_ in ops)
    return [(i1, j2 - j1) for tag, i1, _, j1, j2 in ops if tag == "insert"]


def _without_m73(text: str) -> str:
    return "".join(x for x in text.splitlines(keepends=True) if not x.startswith("M73"))


P14 = {
    "P1 and P3, after_layer with M73": (lambda: sample_text(rrf=False), lambda: [insert()], {}),
    "P2, end_of_print": (lambda: sample_text(rrf=False),
                         lambda: [insert(x=150.0, y=150.0, z_top=12.2, bottom_z=12.2)],
                         {"timing": "end_of_print"}),
    "P4, no M73": (lambda: _without_m73(sample_text(rrf=False)), lambda: [insert()],
                   {"preheat_layers": 2}),
    "P5, no labels": (lambda: gcode_ring(roof_z=None, top_z=7.4),
                      lambda: [ring_insert(*CENTRE)], {"insert_temp": 230.0}),
}


@pytest.mark.parametrize("case", P14)
def test_p14_klipper_lines_go_where_the_rrf_lines_go(case):
    make_text, make_inserts, change = P14[case]
    text = make_text()
    rrf = place.place(text, make_inserts(), measured(**change))
    klipper = place.place(text, make_inserts(), measured(firmware="klipper", **change))
    assert (rrf.status, klipper.status) == ("success", "success"), klipper.message
    at_rrf, at_klipper = insertion_points(text, rrf.text), insertion_points(text, klipper.text)
    assert [i for i, _ in at_rrf] == [i for i, _ in at_klipper]
    out = lines(klipper)
    assert sum(x.startswith("HEATSET_CONFIG KEY=M3x5.7 TOOL=3") for x in out) == 1
    assert sum(x.startswith("HEATSET_PREHEAT TEMP=") for x in out) == 1
    assert sum(x == "_HS_PUSH_TICK" for x in out) == 26
    assert not any("M98 " in x for x in out[at_klipper[0][0]:])


def test_p14_klipper_object_names_come_from_exclude_object():
    result = place.place(sample_text(rrf=False), [insert()], measured(firmware="klipper"))
    out = lines(result)
    start = next(i for i, x in enumerate(out) if x.startswith("HEATSET_INSERT_START"))
    assert out[start] == ("HEATSET_INSERT_START INDEX=1 OBJECT=Configuration_1.step_id_0_copy_0 "
                          "X=164.706 Y=158.320 Z_TOP=3.000")
    begin = next(i for i, x in enumerate(out) if x.startswith("HEATSET_BEGIN"))
    assert out[begin - 2] == "EXCLUDE_OBJECT_END NAME=Configuration_1.step_id_0_copy_0"
