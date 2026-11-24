"""The RepRapFirmware G-code (heatsetcore.emit) against the RRF form of the spec's worked
example, approved on 24 Nov 2026 (docs/heatset-plan.md, "Emitted lines").

Worked example: defaults with the placeholder for every TBD; PETG at 245 °C; tool 3; one
insert on object bracket_1 at X 120, Y 80, z_top 12.4; end_of_print; tallest printed
point 12.4.
"""

from pathlib import Path

import pytest

from heatsetcore import emit, profile, routine

GOLDEN = Path(__file__).parent / "data" / "heatset_golden_rrf.gcode"


def example_profile(**change):
    p = profile.default_profile()
    p.update(change)
    assert profile.validate_profile(p) == []
    return p


def example_block(p, inserts=None):
    inserts = inserts or (emit.Insert("bracket_1", 120.0, 80.0, 12.4),)
    return emit.Block(number=1, timing="end_of_print", z_safe=routine.z_safe(p, 12.4),
                      inserts=tuple(inserts))


def test_golden_file_byte_for_byte():
    p = example_profile()
    text = "\n".join(emit.block_lines(p, example_block(p), 245.0)) + "\n"
    assert text == GOLDEN.read_text(encoding="utf-8")


def test_header_commands():
    p = example_profile()
    lines = emit.header_lines(p, total_inserts=1, temp=245.0, version="0.2.6")
    assert lines[0] == '; HEATSET profile "Concept D" heatsetcore 0.2.6'
    assert lines[-2:] == [
        'M98 P"heatset/config.g" K"M3x5.7" H3 D0.400 O0.000 U0.500 W5 Q"warn" B"normal" '
        'L10.000',
        'M98 P"heatset/require.g" K"M3x5.7" C1 S245']


def test_header_comments_list_every_profile_value_then_the_derived_ones():
    p = example_profile()
    lines = emit.header_lines(p, 1, 235.0, "0.2.6", temp_source="print temperature 220 °C")
    comments = [line for line in lines if line.startswith("; ")]
    named = {line[2:].split(" = ")[0] for line in comments[1:]}
    variables = {n for group in profile.GROUPS.values() for n in group}
    assert variables | {"name", "tbd", "L", "push", "ticks", "insert_temp_used"} <= named
    assert "; insert_temp = auto" in comments and "; push = 5.4" in comments
    assert "; ticks = 26" in comments
    assert "; filament_temps = PLA 225, PETG 245, ABS 265, ASA 265" in comments
    assert "; insert_temp_used = 235 (print temperature 220 °C)" in comments
    assert all(line.startswith((";", "M98")) for line in lines)


def test_rehearse_differs_only_in_the_mode():
    def whole(p):
        return emit.header_lines(p, 1, 245.0, "0.2.6") + emit.block_lines(
            p, example_block(p), 245.0)

    normal, rehearse = whole(example_profile()), whole(example_profile(mode="rehearse"))
    changed = [(a, b) for a, b in zip(normal, rehearse, strict=True) if a != b]
    assert len(changed) == 2
    assert changed[0] == ("; mode = normal", "; mode = rehearse")
    assert changed[1][0].replace('B"normal"', 'B"rehearse"') == changed[1][1]   # config.g


def test_preheat_line():
    assert emit.preheat_line(example_profile(), 245.0) == 'M98 P"heatset/preheat.g" S245'


def test_two_inserts_share_one_visit():
    p = example_profile()
    inserts = (emit.Insert("bracket_1", 120.0, 80.0, 12.4),
               emit.Insert("bracket_1", 140.0, 80.0, 12.4))
    lines = emit.block_lines(p, example_block(p, inserts), 245.0)
    assert lines[1] == 'M98 P"heatset/begin.g" K"M3x5.7" S245 Z17.400 C2'
    assert "; insert 2/2 bracket_1 X140.000 Y80.000 Ztop12.400" in lines
    assert 'M98 P"heatset/insert_start.g" I2 O"bracket_1" X140.000 Y80.000 Z12.400' in lines
    assert [line for line in lines if "begin.g" in line or "end.g" in line] == [lines[1],
                                                                              lines[-1]]
    assert sum("insert_done.g" in line for line in lines) == 2


def test_no_unsheath_when_l_is_zero():
    p = example_profile(proud_after_hot=0.8, mouth_gap=0.8, local_clear=3.0)
    lines = emit.block_lines(p, example_block(p), 245.0)
    assert not any("unsheath.g" in line for line in lines)
    assert 'M98 P"heatset/push.g" D5.700 V0.5 W2.0 C3' in lines        # push = Li + e


def test_quotes_in_an_object_name_are_doubled_in_the_parameter_only():
    p = example_profile()
    lines = emit.block_lines(p, example_block(p, (emit.Insert('lid "A"', 10, 0, 5),)), 245.0)
    assert 'O"lid ""A"""' in lines[3] and lines[2].startswith('; insert 1/1 lid "A" X10.000')


@pytest.mark.parametrize(("value", "text"), [(0.0, "0.000"), (-1e-12, "0.000"),
                                             (-10.0, "-10.000"), (1e-7, "0.000"),
                                             (123456.7891, "123456.789")])
def test_lengths_never_in_exponent_form_or_negative_zero(value, text):
    assert emit.length(value) == text


def test_temperatures_and_feeds():
    assert (emit.temperature(245.0), emit.temperature(232.5), emit.temperature(5)) == (
        "245", "232.5", "5")
    assert (emit.feed(150), emit.feed(0.5), emit.feed(2.0)) == ("9000", "30", "120")


def test_every_speed_comes_from_the_profile():
    p = example_profile(xy_travel_speed=100.0, z_local_speed=4.0, push_speed=0.7)
    lines = emit.block_lines(p, example_block(p), 245.0)
    assert "G0 X100.000 Y80.000 F6000" in lines and "G0 Z14.800 F240" in lines
    assert 'M98 P"heatset/push.g" D5.400 V0.7 W2.0 C3' in lines


def test_klipper_comes_later():
    p = example_profile(firmware="klipper")
    with pytest.raises(NotImplementedError, match="milestone 9"):
        emit.block_lines(p, example_block(p), 245.0)
