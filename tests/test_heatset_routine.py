"""Routine math (heatsetcore.routine) against the spec's worked example and heights table."""

import pytest

from heatsetcore import profile, routine


def test_derived_values_of_the_worked_example():
    d = routine.derived(profile.default_profile())
    assert d["L"] == pytest.approx(0.3) and d["push"] == pytest.approx(5.4)
    assert d["ticks"] == 26                                  # ceil(5.4 / 0.25) + 3 + 1
    assert (d["pad_face_in_push"], d["mouth_in_press"]) == (pytest.approx(0.4),
                                                             pytest.approx(0.4))


@pytest.mark.parametrize(("li", "e", "p", "h", "g"), [
    (5.7, 0.0, 0.4, 0.8, 1.1), (3.0, 0.2, 0.3, 0.6, 0.6), (5.7, 0.35, 0.5, 0.9, 1.4),
])
def test_one_insert_per_cycle(li, e, p, h, g):
    p_ = dict(profile.default_profile(), insert_length=li, rest_recess=e, pad_drop=p,
              mouth_gap=h, proud_after_hot=g)
    d = routine.derived(p_)
    assert d["push"] + d["L"] == pytest.approx(li + e)


def test_ticks_round_up_and_add_the_waits():
    p = dict(profile.default_profile(), push_step=0.27, resist_retries=5)
    assert routine.derived(p)["ticks"] == 20 + 5 + 1         # ceil(5.4 / 0.27) = 20
    p = dict(profile.default_profile(), push_step=0.3)       # 5.4 / 0.3 is 18, not 18.000001
    assert routine.derived(p)["ticks"] == 18 + 3 + 1


def test_heights_table_of_the_worked_example():
    """The spec's table "Heights above s in the example, for the routine-math tests"."""
    expected = [("5 Line up", 0.8, 0.4, 6.5), ("6 Hot push", 0.8, 0.4, 1.1),
                ("7 Unsheath", 1.1, 0.7, 1.1), ("9 Lift and swap", 2.6, 2.2, 1.1),
                ("10 Press trip, flush", 0.4, 0.0, 0.0)]
    got = [(row.step, row.mouth, row.pad_face, row.insert_top)
           for row in routine.heights(profile.default_profile())]
    assert [row[0] for row in got] == [row[0] for row in expected]
    for row, want in zip(got, expected, strict=True):
        assert row[1:] == pytest.approx(want[1:], abs=1e-9), row[0]


def test_heights_keep_the_spec_s_clearances():
    """Rule 2: the pad clears the placed insert as it moves over it (step 9)."""
    rows = {row.step: row for row in routine.heights(profile.default_profile())}
    lift = rows["9 Lift and swap"]
    assert lift.pad_face - lift.insert_top >= 0.3 - 1e-9


def test_positions_of_one_insert_in_the_worked_example():
    p = profile.default_profile()
    moves = routine.insert_moves(p, x=120.0, y=80.0, z_top=12.4)
    assert (moves.pad_over_hole_x, moves.pad_over_hole_y) == (pytest.approx(100.0),
                                                               pytest.approx(80.0))
    assert moves.approach_z == pytest.approx(14.8)            # z_top + probe_start + p
    assert moves.lift_height == pytest.approx(2.6)            # g + travel_lift
    assert routine.z_safe(p, 12.4) == pytest.approx(17.4)
