"""Findings for one heat-set insert: the spec's rule 7 and the hold-down warning.

docs/heatset-plan.md, "Checks". Messages give the measurement, the limit and the fix in
CAD, as the nut checker's do (nutcore.checker).
"""

from __future__ import annotations

import math

from nutcore.checker import CHECK_EPS, minimum_finding, range_finding
from nutcore.pocket import OFF_CENTRE
from nutcore.rays import GAP_EPS
from nutcore.report import Finding, finding

from .hole import HoleMeasure
from .insert import InsertFrame

TILTED = "TILTED"


def orientation_finding(label: str, cls: str, tilt_deg: float) -> Finding:
    """Inserts the printer cannot press: a warning and no insert command."""
    if cls == TILTED:
        return finding("W_TILTED", f"{label}: the insert's axis is tilted {tilt_deg:.1f}° from "
                       "vertical. The printer presses inserts straight down, so this insert "
                       "gets no insert command: fit it by hand after the print.")
    return finding("W_INVERTED", f"{label}: the hole opens downward. The printer presses inserts "
                   "from above, so this insert gets no insert command: fit it by hand after "
                   "the print.")


def check_insert(label: str, prof: dict, frame: InsertFrame, m: HoleMeasure,
                 axis_tol_deg: float) -> list[Finding]:
    """Rule 7 for an upright insert, plus what the hole measurement found."""
    out: list[Finding | None] = [finding(code, f"{label}: {text}.") for code, text in m.issues]
    out += [finding(code, f"{label}: {text}.") for code, text in m.notes]
    if m.diameter is not None:
        out.append(range_finding(label, "E_HOLE_DIAMETER", "hole diameter", m.diameter,
                                 prof["hole_d_min"], prof["hole_d_max"]))
    if m.depth is not None and not m.through:
        out.append(minimum_finding(label, "E_DEPTH", "hole depth", m.depth,
                                   prof["insert_length"] + prof["hole_extra_depth"]))
        below = m.s_bottom + frame.length / 2          # > 0: the body reaches past the bottom
        if below > GAP_EPS:
            out.append(finding("E_INTERFERENCE", f"{label}: the insert body reaches {below:.2f} "
                               "mm below the bottom of its hole. Move the body up or make the "
                               "hole deeper in CAD and re-export."))
    if m.wall is not None and m.wall < prof["min_wall"] - CHECK_EPS:
        out.append(finding("E_WALL", f"{label}: the wall around the hole is {m.wall:.2f} mm, "
                           f"and {prof['min_wall']:.2f} mm is needed. Thicken the boss in CAD "
                           "and re-export."))
    if m.surface_tilt is not None and m.surface_tilt > axis_tol_deg + 1e-9:
        out.append(finding("E_SURFACE", f"{label}: the surface around the hole slopes "
                           f"{m.surface_tilt:.1f}° from level, more than {axis_tol_deg:.1f}°. "
                           "The pad probes and presses on it: make it flat in CAD."))
    if m.offset > OFF_CENTRE:
        out.append(finding("N_OFF_CENTRE", f"{label}: the insert body is {m.offset:.2f} mm from "
                           "the hole's axis. The hole's axis is used."))
    return [f for f in out if f is not None]


def hold_down_finding(label: str, prof: dict, area: float, height: float) -> Finding | None:
    """A part that a press of trip_force might tip or pull off the bed."""
    ratio = height / math.sqrt(area) if area > 0 else math.inf
    if (area >= prof["min_contact_area"] - CHECK_EPS
            and ratio <= prof["max_height_ratio"] + CHECK_EPS):
        return None
    return finding("W_HOLD_DOWN", f"{label}: the part stands on {area:.0f} mm² of bed and is "
                   f"{height:.1f} mm tall, so a {prof['trip_force']:.0f} g press may tip it or "
                   f"lift it off the bed (limits: {prof['min_contact_area']:.0f} mm² and height "
                   f"÷ √area {prof['max_height_ratio']:.1f}; here {ratio:.1f}). Add a brim, or "
                   "fit this insert by hand.")
