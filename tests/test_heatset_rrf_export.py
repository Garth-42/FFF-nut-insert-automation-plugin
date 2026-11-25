"""Placement on a real RepRapFirmware export: the plan's "Found in a real Orca export".

The placement rules were written against `tests/data/sample.gcode`, a Klipper-flavour
export, and RRF variants made from it. `tests/data/sample_rrf.gcode` is the file from
manual check G: the bring-up coupon exported by the plugin from OrcaSlicer with the RRF
printer profile, heat-set lines included. Until that file exists these tests skip.
"""

import re
from pathlib import Path

import pytest

from heatsetcore import place
from nutcore.gcode.parser import parse
from nutcore.gcode.place import first_object_start, object_label_at

SAMPLE_RRF = Path(__file__).parent / "data" / "sample_rrf.gcode"

pytestmark = pytest.mark.skipif(
    not SAMPLE_RRF.exists(),
    reason="no real RRF export yet: save manual check G's file as tests/data/sample_rrf.gcode")

_BLOCK = re.compile(r"; HEATSET block \d+: ")
_FW_RETRACT = re.compile(r"G10\s*(;|$)")


@pytest.fixture(scope="module")
def text() -> str:
    return SAMPLE_RRF.read_bytes().decode("utf-8", "surrogateescape")


@pytest.fixture(scope="module")
def parsed(text):
    return parse(text)


def _blocks(parsed) -> list[int]:
    return [i for i, x in enumerate(parsed.lines) if _BLOCK.match(x)]


def test_it_is_an_rrf_export_with_heat_set_lines(parsed):
    assert not any(x.startswith("EXCLUDE_OBJECT") for x in parsed.lines)
    assert any(x.startswith('M98 P"heatset/') for x in parsed.lines)
    assert _blocks(parsed), "no heat-set block: export with the insert body set to Modifier"


def test_finding_4_header_before_the_first_object_label(parsed):
    head = next(i for i, x in enumerate(parsed.lines) if x.startswith(place.HEADER_MARK))
    first = first_object_start(parsed)
    assert first is not None, "Orca wrote no object labels: turn on label objects"
    assert head < first


def test_finding_1_no_object_is_current_at_a_block(parsed):
    for line in _blocks(parsed):
        assert object_label_at(parsed, line) == "", f"block at line {line + 1} is inside an object"


def test_finding_1_the_print_tool_has_retracted_before_a_block(parsed):
    extruding = parsed.seg_line[parsed.seg_extruding]
    for line in _blocks(parsed):
        last = int(extruding[extruding < line].max())
        between = range(last + 1, line)
        assert any(parsed.line_de[i] < 0 or _FW_RETRACT.match(parsed.lines[i].strip())
                   for i in between), f"no retract before the block at line {line + 1}"


def test_finding_2_preheat_comes_before_the_first_block(parsed):
    heat = next(i for i, x in enumerate(parsed.lines) if x.startswith('M98 P"heatset/preheat.g"'))
    assert heat < _blocks(parsed)[0]


def test_finding_5_the_insert_temperature_is_recorded(parsed):
    assert any(x.startswith("; insert_temp_used = ") for x in parsed.lines)


def test_p12_a_second_run_leaves_the_file_alone(text):
    result = place.place(text, [], {})
    assert (result.status, result.text) == (place.SKIPPED, text)
