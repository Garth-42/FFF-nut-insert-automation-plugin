"""Routine math: the derived values and the heights of the insertion routine.

docs/HEATSET_GCODE_SPEC.md, "Derived, never typed" and "The insertion routine". Heights
in the routine after the probe (step 4) are above s, the surface the pad probe finds; the
G-code's own moves before it are bed heights. Every number the emitter writes comes from
the profile, the model, or a function here.

Symbols: Li insert length, e rest recess, p pad drop, h mouth gap, g proud after the hot
stage, L unsheath lift, r follower retract.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EPS = 1e-9


def derived(profile: dict) -> dict:
    """The spec's derived values. Never typed in; the header prints them."""
    li, e = profile["insert_length"], profile["rest_recess"]
    p, h, g = profile["pad_drop"], profile["mouth_gap"], profile["proud_after_hot"]
    lift = g - h                                       # L: unsheath lift and follower feed
    push = h + e + li - g                              # follower travel in the hot push
    assert abs(push + lift - (li + e)) < 1e-9          # one insert per cycle
    ticks = math.ceil(push / profile["push_step"] - EPS) + profile["resist_retries"] + 1
    return {"L": lift, "push": push, "ticks": ticks,
            "pad_face_in_push": h - p,                 # pad face above the surface, hot push
            "mouth_in_press": p}                       # mouth above the surface, cold press


@dataclass(frozen=True)
class Heights:
    """Where things are after a step of the routine, in mm above the probed surface s."""

    step: str
    mouth: float
    pad_face: float
    insert_top: float     # the insert being placed


def heights(profile: dict) -> list[Heights]:
    """The spec's heights table: mouth, pad face and insert top after the steps that move them."""
    li, e = profile["insert_length"], profile["rest_recess"]
    p, h, g = profile["pad_drop"], profile["mouth_gap"], profile["proud_after_hot"]
    lift = g - h
    above = g + profile["travel_lift"]
    return [
        Heights("5 Line up", h, h - p, h + e + li),       # the insert still inside the tube
        Heights("6 Hot push", h, h - p, g),
        Heights("7 Unsheath", h + lift, h + lift - p, g),
        Heights("9 Lift and swap", above, above - p, g),
        Heights("10 Press trip, flush", p, 0.0, 0.0),
    ]


def z_safe(profile: dict, tallest_printed_z: float) -> float:
    """Mouth height for moves between inserts: the tallest printed point so far + clearance."""
    return tallest_printed_z + profile["safe_z_clear"]


@dataclass(frozen=True)
class InsertMoves:
    """The numbers one insert's routine writes, from its hole point and the profile."""

    pad_over_hole_x: float     # step 2 and 9: the mouth here puts the pad over (x, y)
    pad_over_hole_y: float
    approach_z: float          # step 3: the pad face probe_start above z_top
    lift_height: float         # step 9: mouth above s before the pad moves over the insert


def insert_moves(profile: dict, x: float, y: float, z_top: float) -> InsertMoves:
    return InsertMoves(
        pad_over_hole_x=x - profile["pad_dx"],
        pad_over_hole_y=y - profile["pad_dy"],
        approach_z=z_top + profile["probe_start"] + profile["pad_drop"],
        lift_height=profile["proud_after_hot"] + profile["travel_lift"])
