"""Where insert blocks go (nutcore/gcode/place.py, DECISIONS.md #39).

A block goes after the layer's retract, wipe and object label, outside every label a
firmware uses to cancel an object, and never inside the end G-code.

The real export is Klipper-flavoured. The RepRapFirmware variants are made from it: with
the EXCLUDE_OBJECT lines removed RRF reads the comment labels, and with M486 commands in
their place it reads those. A real RRF export should confirm them once there is one.
"""

from pathlib import Path

import pytest

from builders import sample_record
from nutcore import library
from nutcore.gcode.inject import BEGIN, inject
from nutcore.gcode.parser import parse
from nutcore.gcode.place import block_after
from nutcore.report import Report

SAMPLE = Path(__file__).parent / "data" / "sample.gcode"
END_LABEL = "EXCLUDE_OBJECT_END NAME=Configuration_1.step_id_0_copy_0"
RETRACT = "G1 E-.60053 F1800"              # the end of the layer at Z 3.0 in the sample
WIPE = "G1 X112.068 Y125.165 E-.19947"


def sample() -> list[str]:
    return SAMPLE.read_bytes().decode("utf-8", "surrogateescape").splitlines(keepends=True)


def around_block(text: str, z: float | None):
    """(line before the block, line after it, lines up to the block, lines after it).

    z picks the layer: its last extruding line at or below z. None means the last layer.
    """
    parsed = parse(text)
    if z is None:
        last = parsed.last_extruding_line
    else:
        seg, line = parsed.extruding
        last = int(line[seg[:, 5] <= z + 1e-3].max())
    i = block_after(parsed, last)
    after = parsed.lines[i + 1].strip() if i + 1 < len(parsed.lines) else None
    return parsed.lines[i].strip(), after, parsed.lines[:i + 1], parsed.lines[i + 1:]


def without_klipper_labels() -> list[str]:
    return [line for line in sample() if not line.startswith("EXCLUDE_OBJECT")]


def test_klipper_labels():
    before, after, head, _ = around_block("".join(sample()), 3.0)
    assert (before, after) == (END_LABEL, ";AFTER_LAYER_CHANGE")
    recent = [line.strip() for line in head[-12:]]
    assert RETRACT in recent and WIPE in recent          # retracted and wiped


def test_comment_labels_as_reprapfirmware_reads_them():
    before, after, head, tail = around_block("".join(without_klipper_labels()), 3.0)
    assert (before, after) == (WIPE, ";WIPE_END")
    assert any(line.startswith("; stop printing object") for line in head[-14:])
    assert next(line for line in tail if "printing object" in line).startswith(
        "; printing object")                             # the next layer's label comes after


def test_m486_labels():
    lines = []
    for line in without_klipper_labels():
        if line.startswith("; stop printing object"):
            line = "M486 S-1\n"
        elif line.startswith("; printing object"):
            line = "M486 S0\n"
        lines.append(line)
    before, _, head, tail = around_block("".join(lines), 3.0)
    assert before == WIPE
    assert "M486 S-1\n" in head[-14:]
    assert next(line for line in tail if line.startswith("M486")) == "M486 S0\n"


def test_a_macro_between_layers_is_passed_over():
    lines = sample()
    at = next(i for i, line in enumerate(lines) if line.startswith(";Z:3.2"))
    lines.insert(at + 1, "TIMELAPSE_TAKE_FRAME\n")
    assert around_block("".join(lines), 3.0)[:2] == (END_LABEL, ";AFTER_LAYER_CHANGE")


def test_end_of_print_stays_before_the_end_gcode():
    before, after, _, tail = around_block("".join(sample()), None)
    assert (before, after) == (END_LABEL, "M106 S0")
    assert any(line.startswith("PRINT_END") for line in tail)


def two_layers(*between: str) -> str:
    """Two layers of one line each; `between` follows the first layer's retract."""
    return "\n".join(["G90", "M83", "G1 Z0.2 F600", "G1 X0 Y0 F9000", "G1 X10 Y0 E1",
                      "G1 E-0.8 F1800", *between, "G1 Z0.4 F600", "G1 X0 Y0 E1",
                      "G1 E-0.8 F1800", "M104 S0"]) + "\n"


@pytest.mark.parametrize(("between", "before", "after"), [
    ((), "G1 E-0.8 F1800", "G1 Z0.4 F600"),
    (("T1",), "G1 E-0.8 F1800", "T1"),
    (("G91", "G1 X1 Y0", "G90"), "G1 E-0.8 F1800", "G91"),
    (("G1 X5 Y5 F9000", "G1 E0.8 F1800"), "G1 E-0.8 F1800", "G1 X5 Y5 F9000"),
    (("M117 next layer", "; stop printing object A"), "; stop printing object A",
     "G1 Z0.4 F600"),
])
def test_what_stops_a_block_and_what_it_passes(between, before, after):
    assert around_block(two_layers(*between), 0.2)[:2] == (before, after)


def test_firmware_retraction():
    """A bare G10 retracts and G11 primes; G10 with parameters sets tool temperatures."""
    layers = ["G90", "M83", "G1 Z0.2 F600", "G1 X0 Y0 F9000", "G1 X10 Y0 E1", "G10"]
    after_layer = ["G1 Z0.4 F600", "G1 X0 Y0 E1", "M104 S0"]
    text = "\n".join([*layers, "G10 P0 S215", *after_layer]) + "\n"
    assert around_block(text, 0.2)[:2] == ("G10", "G10 P0 S215")
    text = "\n".join([*layers, "G11", *after_layer]) + "\n"
    assert around_block(text, 0.2)[:2] == ("G10", "G11")


def test_inline_end_gcode_is_not_entered():
    text = "\n".join(["G90", "M83", "G1 Z0.2 F600", "G1 X0 Y0 F9000", "G1 X10 Y0 E1",
                      "G1 E-0.8 F1800", "M104 S0", "G91", "G1 E-2 F2700", "G1 Z10",
                      "G90"]) + "\n"
    assert around_block(text, None)[:2] == ("G1 E-0.8 F1800", "M104 S0")


def test_reprapfirmware_nut_line_on_comment_labels():
    """The nut export end to end with the RRF template, on the variant RRF reads labels from."""
    config = library.default_config()
    config["settings"]["firmware"] = "reprapfirmware"
    result = inject("".join(without_klipper_labels()), Report(nuts=[sample_record()]),
                    library.parse(config))
    assert result.status == "success", result.message
    lines = result.text.splitlines()
    at = lines.index(f"{BEGIN} layer_z=3.000 count=1")
    assert lines[at - 1] == WIPE
    assert lines[at + 1] == ('M98 P"insert_nut.g" K"M3SQ" C"FLAT" X164.706 Y158.320 Z1.900 '
                             'L1.000 A0.00 F1 S-1')
