"""Detection cases 1 to 20 from docs/SPEC.md, all with the M3SQ placeholder entry."""

import numpy as np
import pytest

from builders import box, nut, pocket_block, snapshot, v_slot
from nutcore import library
from nutcore.mesh import rotation, scaling, translation
from nutcore.pipeline import detect

FLOOR = 4.4                       # floor slab thickness, so the pocket floor is at Z 4.4
BED = translation((112.4, 87.25, FLOOR))
NUT_Z = 0.9                       # nut centre above the floor: half of 1.8
TOL = 1e-6


def codes(record):
    return [f.code for f in record.findings]


def run(parts, matrices=None, config=None):
    return detect(snapshot(parts, matrices or [BED]), config or library.default_config())


def flat_case(inner=(5.8, 5.8, 2.0), nut_centre=(0, 0, NUT_Z), matrices=None, config=None, **kw):
    return run([pocket_block(inner=inner, **kw), nut(centre=nut_centre)], matrices, config)


def test_case_01_flat_nut_in_roofed_pocket():
    report = flat_case()
    (n,) = report.nuts
    assert (n.cls, n.status, n.key, n.findings) == ("FLAT", "ok", "M3SQ", [])
    assert n.placement == pytest.approx([112.4, 87.25, 5.3], abs=TOL)
    assert n.yaw_deg == pytest.approx(0.0, abs=TOL)
    assert (n.z_low, n.z_high, n.roof_z, n.rim_z) == (
        pytest.approx(4.4, abs=TOL), pytest.approx(6.2, abs=TOL), pytest.approx(6.4, abs=TOL),
        None)
    assert n.pocket["width"] == pytest.approx([5.8, 5.8], abs=TOL)
    assert n.pocket["depth"] == pytest.approx(2.0, abs=TOL)
    assert n.box["centre"] == pytest.approx([112.4, 87.25, 5.4], abs=TOL)
    assert n.box["half"] == pytest.approx([2.9, 2.9, 1.0], abs=TOL)
    assert n.window == pytest.approx([6.3, 6.4], abs=TOL)
    assert report.summary == {"ok": 1, "warning": 0, "error": 0}


def test_case_02_object_rotated_30_about_z():
    origin = (10.0, 5.0, 0.0)
    matrix = BED @ rotation("z", 30)
    report = run([pocket_block(origin=origin), nut(centre=(10, 5, NUT_Z))], [matrix])
    (n,) = report.nuts
    assert n.status == "ok"
    assert n.yaw_deg == pytest.approx(30.0, abs=1e-6)
    assert f"{n.yaw_deg:.2f}" == "30.00"
    expected = (matrix @ np.array([10, 5, NUT_Z, 1.0]))[:3]
    assert n.placement == pytest.approx(expected.tolist(), abs=TOL)


def test_case_03_body_shifted_keeps_placement():
    (n,) = flat_case(nut_centre=(0.15, 0, NUT_Z)).nuts
    assert n.placement == pytest.approx([112.4, 87.25, 5.3], abs=TOL)
    assert n.modelled_centre == pytest.approx([112.55, 87.25, 5.3], abs=TOL)
    assert codes(n) == ["N_OFF_CENTRE"]
    assert n.status == "ok"       # a note does not change the status


def test_case_04_pocket_too_wide():
    (n,) = flat_case(inner=(6.2, 5.8, 2.0)).nuts
    assert codes(n) == ["E_WIDTH"]
    message = n.findings[0].message
    assert all(text in message for text in ("6.20", "5.70", "5.90", "Reduce by 0.30"))
    assert n.status == "error"


def test_case_05_pocket_too_shallow():
    (n,) = flat_case(inner=(5.8, 5.8, 1.9)).nuts
    assert codes(n) == ["E_DEPTH"]


def test_case_06_body_modelled_above_floor_is_settled():
    (n,) = flat_case(nut_centre=(0, 0, NUT_Z + 0.1)).nuts
    assert n.status == "ok" and n.findings == []
    assert n.z_low == pytest.approx(4.4, abs=TOL)
    assert n.pocket["seat_gaps"] == pytest.approx([0.1], abs=TOL)


def test_case_07_bolt_hole_through_floor():
    (n,) = flat_case(bolt_hole=3.4).nuts
    assert n.status == "ok" and n.findings == []
    assert n.z_low == pytest.approx(4.4, abs=TOL)


@pytest.mark.parametrize("heading", [0.0, 45.0])
def test_case_08_nut_on_edge(heading):
    parts = [pocket_block(inner=(2.1, 5.8, 6.0)),
             nut(centre=(0, 0, 2.75), rot=rotation("y", 90))]
    (n,) = run(parts, [BED @ rotation("z", heading)]).nuts
    assert (n.cls, n.status, n.findings) == ("EDGE", "ok", [])
    assert n.yaw_deg == pytest.approx(heading, abs=1e-6)
    assert n.placement == pytest.approx([112.4, 87.25, 4.4 + 2.75], abs=TOL)
    assert n.pocket["thickness"] == pytest.approx(2.1, abs=TOL)
    assert n.pocket["width"] == pytest.approx([5.8], abs=TOL)
    assert n.pocket["depth"] == pytest.approx(6.0, abs=TOL)


def test_case_09_object_tilted():
    (n,) = flat_case(matrices=[BED @ rotation("x", 20)]).nuts
    assert (n.cls, codes(n), n.status) == ("TILTED", ["W_TILTED"], "warning")
    assert n.placement is None
    assert n.tilt_deg == pytest.approx(20.0, abs=1e-6)


def test_case_10_on_edge_nut_rolled():
    parts = [pocket_block(inner=(2.1, 7.0, 7.0)),
             nut(centre=(0, 0, 3.5), rot=rotation("x", 20) @ rotation("y", 90))]
    (n,) = run(parts).nuts
    assert (n.cls, codes(n)) == ("ROLLED", ["W_ROLLED"])
    assert n.roll_deg == pytest.approx(20.0, abs=1e-6)
    assert n.placement is None


def test_case_11_scaled_instance():
    (n,) = flat_case(matrices=[BED @ scaling(1.02)]).nuts
    assert codes(n) == ["E_BODY_SIZE"]
    assert "5.61" in n.findings[0].message


def test_case_12_unknown_key():
    report = run([pocket_block(), nut(centre=(0, 0, NUT_Z), name="NUT_M4SQ")])
    (n,) = report.nuts
    assert codes(n) == ["E_NAME_UNKNOWN"]
    assert n.key is None and n.box is not None


def test_case_13_pocket_narrower_than_nut():
    (n,) = flat_case(inner=(5.3, 5.8, 2.0)).nuts
    assert "E_INTERFERENCE" in codes(n)
    assert n.status == "error"


def test_case_14_nut_without_host():
    (n,) = run([nut(centre=(0, 0, NUT_Z))]).nuts
    assert codes(n) == ["E_NO_POCKET"]


def test_case_14b_pocket_open_on_one_side():
    wall_less = pocket_block(inner=(5.8, 40.0, 2.0))     # walls in Y are out of reach
    (n,) = run([wall_less, nut(centre=(0, 0, NUT_Z))]).nuts
    assert set(codes(n)) == {"E_NO_POCKET"}
    assert "open towards" in n.findings[0].message


def test_case_15_mirrored_instance():
    (plain,) = flat_case().nuts
    mirror = np.diag([-1.0, 1.0, 1.0, 1.0])
    report = flat_case(matrices=[BED @ mirror])
    (n,) = report.nuts
    assert (n.cls, n.status, n.findings) == ("FLAT", "ok", [])
    assert n.placement == pytest.approx(plain.placement, abs=TOL)
    assert n.yaw_deg == pytest.approx(plain.yaw_deg, abs=TOL)
    assert n.pocket["width"] == pytest.approx(plain.pocket["width"], abs=TOL)


def test_case_16_two_instances():
    report = flat_case(matrices=[BED, translation((40, 30, FLOOR))])
    first, second = report.nuts
    assert (first.index, first.instance, second.index, second.instance) == (1, 1, 2, 2)
    assert first.placement == pytest.approx([112.4, 87.25, 5.3], abs=TOL)
    assert second.placement == pytest.approx([40, 30, 5.3], abs=TOL)


def test_case_17_open_top_pocket():
    (n,) = flat_case(roof=None).nuts
    assert n.status == "ok" and n.findings == []
    assert n.roof_z is None
    assert n.rim_z == pytest.approx(6.4, abs=TOL)
    assert n.pocket["depth"] == pytest.approx(2.0, abs=TOL)
    assert n.window[1] is None


def test_case_18_ledge_over_a_third_of_the_pocket():
    third = 5.8 / 3
    ledge = box((third, 5.8, 0.1), (-2.9 + third / 2, 0, 1.95))
    (n,) = flat_case(extra=[ledge]).nuts
    assert codes(n) == ["E_DROP_PATH"]


def test_case_19_class_disabled():
    config = library.default_config()
    config["nuts"][0]["flat"]["enabled"] = False
    (n,) = flat_case(config=config).nuts
    assert codes(n) == ["E_CLASS_DISABLED"]


@pytest.mark.parametrize("g1, g2", [(0.1, 0.1), (0.1, 0.04)])
def test_case_20_corner_nut_in_v_slot(g1, g2):
    """g1 is the gap under the flat on the +Y side, g2 under the flat on the -Y side."""
    parts = [v_slot(gap_plus_y=g1, gap_minus_y=g2),
             nut(rot=rotation("x", 45) @ rotation("y", 90))]
    shift = translation((112.4, 87.25, 10.0))
    (n,) = run(parts, [shift]).nuts
    assert (n.cls, n.status, n.findings) == ("CORNER", "ok", [])
    assert n.yaw_deg == pytest.approx(0.0, abs=1e-6)
    assert n.roll_deg == pytest.approx(45.0, abs=1e-6)
    # Thread axis +X, so h = a x z = -Y. The spec's seat formula:
    d_z = -(g1 + g2) / np.sqrt(2)
    d_h = (g2 - g1) / np.sqrt(2)
    assert n.placement == pytest.approx([112.4, 87.25 - d_h, 10.0 + d_z], abs=TOL)
    r = 5.5 / np.sqrt(2)
    assert n.z_low == pytest.approx(10.0 + d_z - r, abs=TOL)
    assert sorted(n.pocket["seat_gaps"]) == pytest.approx(sorted([g1, g2]), abs=TOL)
    assert n.pocket["thickness"] == pytest.approx(2.1, abs=TOL)
    assert n.pocket["width"] == pytest.approx([8.08], abs=TOL)
    assert n.pocket["depth"] == pytest.approx(14.5 - n.z_low, abs=TOL)


def test_corner_seat_gap_too_large():
    parts = [v_slot(gap_plus_y=0.3, gap_minus_y=0.1),
             nut(rot=rotation("x", 45) @ rotation("y", 90))]
    (n,) = run(parts, [translation((50, 50, 10))]).nuts
    assert "E_SEAT" in codes(n)


def test_report_round_trips_through_json_and_csv():
    from nutcore.report import Report

    report = flat_case(nut_centre=(0.15, 0, NUT_Z))
    again = Report.from_json(report.to_json())
    assert again.to_dict() == report.to_dict()
    assert report.to_dict()["schema"] == 1
    lines = report.to_csv().splitlines()
    assert lines[0].startswith("index,name,key")
    assert "N_OFF_CENTRE" in lines[1]


def test_parts_without_nuts_give_an_empty_report():
    report = run([pocket_block()])
    assert report.nuts == [] and report.summary == {"ok": 0, "warning": 0, "error": 0}


def test_nut_body_that_still_prints_is_an_error():
    from dataclasses import replace

    printing = replace(nut(centre=(0, 0, NUT_Z)), kind="part")
    (n,) = run([pocket_block(), printing]).nuts
    assert codes(n) == ["E_NOT_MODIFIER"] and n.status == "error"
    assert "Modifier" in n.findings[0].message
    assert n.placement == pytest.approx([112.4, 87.25, 5.3], abs=TOL)   # still measured
    as_modifier = replace(printing, kind="modifier")
    assert run([pocket_block(), as_modifier]).nuts[0].status == "ok"


def test_modifiers_that_are_not_nuts_are_not_walls():
    from dataclasses import replace

    blocker = replace(pocket_block(name="Support blocker"), kind="modifier")
    (n,) = run([blocker, nut(centre=(0, 0, NUT_Z))]).nuts
    assert codes(n) == ["E_NO_POCKET"]


def test_nut_body_with_a_round_hole_and_many_facets():
    """A real nut model: the probe found 5,818 triangles in Garth's NUT_M3SQ body."""
    import time

    from builders import merge, part
    from nutcore.mesh import Mesh

    sides = 720
    angle = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    ring = np.column_stack([1.25 * np.cos(angle), 1.25 * np.sin(angle)])
    vertices = np.vstack([np.column_stack([ring, np.full(sides, -0.9)]),
                          np.column_stack([ring, np.full(sides, 0.9)])])
    i = np.arange(sides)
    j = (i + 1) % sides
    hole = Mesh(vertices, np.vstack([np.column_stack([i, j, i + sides]),
                                     np.column_stack([j, j + sides, i + sides])]))
    body = merge([box((5.5, 5.5, 1.8)), hole])
    body = Mesh(body.vertices + np.array([0, 0, NUT_Z]), body.triangles)
    start = time.perf_counter()
    (n,) = run([pocket_block(bolt_hole=3.4), part("NUT_M3SQ", body)]).nuts
    assert (n.cls, n.status, n.findings) == ("FLAT", "ok", [])
    assert n.placement == pytest.approx([112.4, 87.25, 5.3], abs=TOL)
    assert time.perf_counter() - start < 0.1
