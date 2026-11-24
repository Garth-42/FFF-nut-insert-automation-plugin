"""Heat-set detection: cases H1 to H20 from docs/heatset-plan.md, "Tests", with the default
M3x5.7 profile (Ø4.6 x 5.7 insert, hole Ø3.9-4.2 and 6.7 deep, wall 1.6, pad Ø10)."""

import time
from dataclasses import replace

import numpy as np
import pytest

from builders import hole_block, insert_body, snapshot
from heatsetcore.detect import detect_inserts, footprint
from heatsetcore.insert import BodySizeError, insert_frame
from nutcore import library
from nutcore.mesh import apply_matrix, rotation, scaling, translation
from nutcore.rays import cast, cast_fan
from nutcore.report import Report

LIB = library.parse(library.default_config())
BED = translation((100.0, 80.0, 0.0))
TOP = 10.0                              # hole_block's top face
FLUSH = (0.0, 0.0, TOP - 5.7 / 2)       # body middle for an insert flush with the top
TOL = 1e-6
FACETED = (3.99, 4.0 + TOL)             # a 64-facet Ø4 hole measures a little under 4


def codes(record):
    return [f.code for f in record.findings]


def message(record, code):
    return next(f.message for f in record.findings if f.code == code)


def run(parts, matrices=None):
    return detect_inserts(snapshot(parts, matrices or [BED]), LIB)


def one(parts, matrices=None):
    (record,) = run(parts, matrices)
    return record


def blind(**hole):
    return one([hole_block(**hole), insert_body(centre=FLUSH)])


def test_h01_insert_flush_in_a_blind_hole():
    r = blind()
    assert (r.kind, r.key, r.cls, r.status, codes(r)) == ("heatset", "M3x5.7", "UPRIGHT", "ok", [])
    assert (r.index, r.object, r.instance, r.part, r.name) == (1, 1, 1, 2, "HEATSET_M3x5.7")
    assert r.placement == pytest.approx([100.0, 80.0, TOP - 2.85], abs=TOL)
    assert (r.z_low, r.z_high) == pytest.approx((TOP - 5.7, TOP), abs=TOL)   # z_top: body top
    assert r.rim_z == pytest.approx(TOP, abs=TOL)
    assert r.window[0] == pytest.approx(TOP, abs=TOL) and r.window[1] is None
    assert r.axis == pytest.approx([0, 0, 1], abs=TOL) and r.tilt_deg == pytest.approx(0, abs=TOL)
    assert r.body_size == pytest.approx([4.6, 4.6, 5.7], abs=TOL)
    p = r.pocket
    assert FACETED[0] < p["diameter"] < FACETED[1]
    assert p["depth"] == pytest.approx(6.7, abs=TOL)
    assert p["bottom_z"] == pytest.approx(TOP - 6.7, abs=TOL)
    assert p["through"] is False
    assert p["wall"] == pytest.approx(4.0, abs=0.02)
    assert p["sink"] == pytest.approx(0.0, abs=TOL)
    assert p["surface_tilt"] == pytest.approx(0.0, abs=1e-6)
    assert r.box["centre"] == pytest.approx([100.0, 80.0, TOP - 6.7 / 2], abs=TOL)
    assert r.box["half"][2] == pytest.approx(6.7 / 2, abs=TOL)


def test_h02_object_rotated_and_moved():
    """The hole sits 5 mm off the object's origin, so the turn moves it."""
    off = translation((5.0, 0.0, 0.0))
    parts = [replace(hole_block(), matrix=off), replace(insert_body(centre=FLUSH), matrix=off)]
    r = one(parts, [translation((150.0, 60.0, 0.0)) @ rotation("z", 30)])
    assert (r.cls, r.status, codes(r)) == ("UPRIGHT", "ok", [])
    assert r.placement == pytest.approx([150 + 5 * np.cos(np.pi / 6), 62.5, TOP - 2.85],
                                        abs=1e-5)


def test_h03_body_off_the_hole_axis_is_placed_on_the_hole():
    r = one([hole_block(), insert_body(centre=(0.15, 0.0, FLUSH[2]))])
    assert (r.status, codes(r)) == ("ok", ["N_OFF_CENTRE"])
    assert "0.15 mm" in message(r, "N_OFF_CENTRE")
    # Two fitting passes, the first from 0.15 mm off: within 0.1 µm of the hole axis.
    assert r.placement == pytest.approx([100.0, 80.0, TOP - 2.85], abs=1e-4)


def test_h04_hole_too_wide():
    r = blind(hole=4.3)
    assert (r.status, codes(r)) == ("error", ["E_HOLE_DIAMETER"])
    text = message(r, "E_HOLE_DIAMETER")
    assert "4.30" in text and "3.90–4.20 mm" in text


def test_h05_blind_hole_too_shallow():
    r = blind(depth=6.5)
    assert (r.status, codes(r)) == ("error", ["E_DEPTH"])
    text = message(r, "E_DEPTH")
    assert "6.50 mm" in text and "6.70 mm or more" in text


def test_h06_hole_steps_down_to_a_screw_hole():
    r = blind(step=(3.4, 7.0))
    assert (r.status, codes(r)) == ("ok", [])
    assert r.pocket["depth"] == pytest.approx(7.0, abs=TOL)
    assert r.pocket["through"] is False


def test_h07_through_hole_needs_no_depth():
    r = one([hole_block(through=True, height=6.0), insert_body(centre=(0, 0, 6.0 - 2.85))])
    assert (r.status, codes(r)) == ("ok", [])
    assert r.pocket["through"] is True
    assert r.pocket["depth"] == pytest.approx(6.0, abs=TOL)


def test_h08_entry_chamfer_belongs_to_the_hole():
    r = blind(chamfer=0.5)
    assert (r.status, codes(r)) == ("ok", [])
    assert r.rim_z == pytest.approx(TOP, abs=TOL)
    assert r.pocket["depth"] == pytest.approx(6.7, abs=TOL)


def test_h09_tilted_object_gets_no_insert_command():
    r = one([hole_block(), insert_body(centre=FLUSH)], [BED @ rotation("x", 20)])
    assert (r.cls, r.status, codes(r)) == ("TILTED", "warning", ["W_TILTED"])
    assert r.tilt_deg == pytest.approx(20.0, abs=1e-6)
    assert "20.0°" in message(r, "W_TILTED")
    assert r.placement is None


def test_h10_hole_in_the_underside():
    r = one([hole_block(), insert_body(centre=FLUSH)],
            [translation((100.0, 80.0, TOP)) @ rotation("x", 180)])
    assert (r.cls, r.status, codes(r)) == ("INVERTED", "warning", ["W_INVERTED"])
    assert r.placement is None


def test_h11_thin_wall():
    r = blind(size=6.0)
    assert codes(r) == ["E_WALL", "W_HOLD_DOWN"]        # 6 x 6 mm is also a small footprint
    assert r.pocket["wall"] == pytest.approx(1.0, abs=0.02)
    assert "1.60 mm is needed" in message(r, "E_WALL")


def test_h12_surface_around_the_hole_slopes():
    r = blind(slope_deg=5.0)
    assert codes(r) == ["E_SURFACE"]
    assert r.pocket["surface_tilt"] == pytest.approx(5.0, abs=1e-6)
    assert "5.0°" in message(r, "E_SURFACE")


def test_h13_scaled_instance():
    r = one([hole_block(), insert_body(centre=FLUSH)], [BED @ scaling(1.02)])
    assert (r.status, codes(r)) == ("error", ["E_BODY_SIZE"])
    text = message(r, "E_BODY_SIZE")
    assert "5.81 mm long and 4.69 mm across" in text and "5.70 mm long and 4.60 mm across" in text
    assert r.placement is None


def test_h14_mirrored_copy_and_two_copies():
    mirrored = translation((140.0, 80.0, 0.0)) @ scaling((-1.0, 1.0, 1.0))
    records = run([hole_block(), insert_body(centre=FLUSH)], [BED, mirrored])
    assert [(r.index, r.instance, r.status, codes(r)) for r in records] == [
        (1, 1, "ok", []), (2, 2, "ok", [])]
    assert records[1].placement == pytest.approx([140.0, 80.0, TOP - 2.85], abs=TOL)
    assert records[1].pocket["depth"] == pytest.approx(6.7, abs=TOL)


def test_h15_body_still_a_printing_part():
    r = one([hole_block(), insert_body(centre=FLUSH, kind="part")])
    assert (r.status, codes(r)) == ("error", ["E_NOT_MODIFIER"])
    assert "Change type, Modifier" in message(r, "E_NOT_MODIFIER")
    assert r.pocket["depth"] == pytest.approx(6.7, abs=TOL)   # not a wall of its own hole


def test_h16_no_profile_for_the_name():
    r = one([hole_block(), insert_body(centre=FLUSH, name="HEATSET_M4x8")])
    assert (r.status, codes(r)) == ("error", ["E_NAME_UNKNOWN"])
    assert "HEATSET_M3x5.7" in message(r, "E_NAME_UNKNOWN")


def test_h17_lid_over_the_hole_with_a_gap():
    r = blind(lid_gap=3.0)
    assert (r.status, codes(r)) == ("ok", ["N_COVERED"])
    assert "3.00 mm above its rim" in message(r, "N_COVERED")


def test_h18_knurled_body_in_a_fine_hole_is_quick():
    detect_inserts(snapshot([hole_block(), insert_body(centre=FLUSH)], [BED]), LIB)  # warm up
    parts = [hole_block(sides=256),
             insert_body(sides=720, bore=2.5, knurl=0.15, centre=FLUSH)]
    start = time.perf_counter()
    r = one(parts)
    assert time.perf_counter() - start < 0.1
    assert (r.status, codes(r)) == ("ok", [])
    assert r.pocket["diameter"] == pytest.approx(4.0, abs=1e-3)


def test_h20_small_tall_part():
    r = one([hole_block(size=8.0, height=30.0), insert_body(centre=(0, 0, 30.0 - 2.85))])
    assert (r.status, codes(r)) == ("warning", ["W_HOLD_DOWN"])
    text = message(r, "W_HOLD_DOWN")
    assert "64 mm² of bed" in text and "30.0 mm tall" in text


# --- More checks ----------------------------------------------------------------------------

def test_body_below_the_bottom_of_its_hole():
    r = one([hole_block(), insert_body(centre=(0, 0, FLUSH[2] - 1.5))])
    assert codes(r) == ["E_INTERFERENCE"]
    assert "0.50 mm below the bottom" in message(r, "E_INTERFERENCE")


def test_body_with_no_hole_around_it():
    r = one([hole_block(), insert_body(centre=(20.0, 0.0, 2.85))])
    assert (r.status, codes(r)) == ("error", ["E_NO_POCKET"])
    assert r.placement is None


def test_hole_closed_at_both_ends():
    r = blind(lid_gap=0.0)
    assert (r.status, codes(r)) == ("error", ["E_DROP_PATH"])
    assert "closed at both ends" in message(r, "E_DROP_PATH")


def test_numbering_follows_the_nuts_and_nuts_are_not_hosts():
    from builders import nut

    parts = [hole_block(), nut(centre=(0.0, 0.0, 1.0)), insert_body(centre=FLUSH)]
    (r,) = detect_inserts(snapshot(parts, [BED]), LIB, first_index=4)
    assert (r.index, r.part, r.status) == (4, 3, "ok")


def test_heat_set_records_survive_json():
    r = blind()
    back = Report.from_json(Report(nuts=[r]).to_json()).nuts[0]
    assert (back.kind, back.cls, back.pocket["through"]) == ("heatset", "UPRIGHT", False)
    assert back.pocket["depth"] == pytest.approx(6.7, abs=TOL)
    row = Report(nuts=[r]).to_csv().splitlines()[1].split(",")
    assert row[-3:] == ["heatset", f"{r.pocket['diameter']:.3f}", f"{r.pocket['wall']:.3f}"]


def test_footprint_of_the_printing_parts():
    host = snapshot([hole_block()], [BED])
    from nutcore.mesh import bed_mesh

    corners = bed_mesh(host.objects[0].parts[0], host.objects[0].instances[0]).corners()
    assert footprint(corners) == pytest.approx((144.0, 10.0), abs=1e-6)
    assert footprint(np.zeros((0, 3, 3))) == (0.0, 0.0)


# --- H19: the insert frame ------------------------------------------------------------------

BODIES = {
    "plain": dict(),
    "bored": dict(bore=2.5),
    "knurled": dict(sides=720, bore=2.5, knurl=0.15),
    "length equals diameter": dict(length=4.6),
}
TURNS = [(np.array([1.0, 0.0, 0.0]), 0.0), (np.array([1.0, 0.0, 0.0]), 20.0),
         (np.array([1.0, 2.0, 0.5]), 37.0), (np.array([0.3, -1.0, 0.2]), 90.0),
         (np.array([0.0, 1.0, 0.0]), 180.0)]


@pytest.mark.parametrize("body", BODIES)
@pytest.mark.parametrize("turn", range(len(TURNS)))
def test_h19_axis_found_for_every_body_and_tilt(body, turn):
    shape = BODIES[body]
    length, od = shape.get("length", 5.7), 4.6
    axis, degrees = TURNS[turn]
    matrix = translation((12.0, -3.0, 7.0)) @ rotation(axis, degrees)
    p = insert_body(**shape)
    frame = insert_frame(apply_matrix(p.vertices, matrix), p.triangles, length, od, 0.05)
    expected = matrix[:3, 2] if matrix[2, 2] >= 0 else -matrix[:3, 2]
    if abs(expected[2]) < 1e-12:                       # lying flat: either way is "up"
        expected = expected if np.dot(frame.axis, expected) > 0 else -expected
    assert frame.axis == pytest.approx(expected, abs=1e-6)
    assert frame.centre == pytest.approx([12.0, -3.0, 7.0], abs=1e-6)
    assert (frame.length, frame.diameter) == pytest.approx((length, od), abs=1e-6)


def test_wrong_body_size_is_reported_with_the_measurement():
    p = insert_body(od=5.0, length=6.0)
    with pytest.raises(BodySizeError) as caught:
        insert_frame(p.vertices, p.triangles, 5.7, 4.6, 0.05)
    assert caught.value.measured == pytest.approx((6.0, 5.0), abs=1e-6)


# --- The fan cast the hole measurement uses -------------------------------------------------

def test_fan_cast_matches_one_cast_per_direction():
    rng = np.random.default_rng(7)
    corners = rng.uniform(-5.0, 5.0, (60, 3, 3))
    axis = np.array([0.1, 0.2, 1.0]) / np.linalg.norm([0.1, 0.2, 1.0])
    centre, s = np.array([0.2, -0.1, 0.3]), np.linspace(-2.0, 2.0, 7)
    dirs = rng.normal(size=(9, 3))
    dirs /= np.linalg.norm(dirs, axis=1)[:, None]
    fan = cast_fan(centre, axis, s, dirs, corners)
    each = np.column_stack([cast(centre + s[:, None] * axis, d, corners) for d in dirs])
    hit = np.isfinite(each)
    assert np.array_equal(np.isfinite(fan), hit) and hit.sum() > 20
    assert fan[hit] == pytest.approx(each[hit], abs=1e-9)
    after = cast_fan(centre, axis, s, dirs, corners, beyond=fan + 1e-6)
    second = np.isfinite(after)
    assert second.sum() > 5 and (after[second] > fan[second]).all()
