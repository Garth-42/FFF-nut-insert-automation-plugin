"""Compare a measured pocket with the library and build findings.

Every message gives the measurement, the allowed range and the fix in CAD.
"""

from __future__ import annotations

import numpy as np

from .frame import CORNER, EDGE, FLAT, ROLLED, TILTED
from .library import NutType, Settings
from .pocket import OFF_CENTRE, Measurement
from .report import Finding, finding

CHECK_EPS = 1e-6  # mm, so 5.7 measured as 5.6999999 still passes


def _range_text(lo: float, hi: float) -> str:
    return f"{lo:.2f}–{hi:.2f} mm"


def range_finding(label: str, code: str, what: str, value: float, lo: float,
                  hi: float) -> Finding | None:
    """An error when value is outside lo..hi, with how far to move it in CAD."""
    if value > hi + CHECK_EPS:
        fix = f"Reduce by {_range_text(value - hi, value - lo)}"
    elif value < lo - CHECK_EPS:
        fix = f"Increase by {_range_text(lo - value, hi - value)}"
    else:
        return None
    return finding(code, f"{label}: {what} {value:.2f} mm, allowed {_range_text(lo, hi)}. "
                         f"{fix} in CAD and re-export.")


def minimum_finding(label: str, code: str, what: str, value: float,
                    lo: float) -> Finding | None:
    if value >= lo - CHECK_EPS:
        return None
    return finding(code, f"{label}: {what} {value:.2f} mm, allowed {lo:.2f} mm or more. "
                         f"Increase by at least {lo - value:.2f} mm in CAD and re-export.")


def orientation_finding(label: str, cls: str, tilt: float, roll: float | None) -> Finding | None:
    if cls == TILTED:
        return finding("W_TILTED", f"{label}: thread axis is tilted {tilt:.1f}° from "
                       "vertical. Only upright or lying nuts can be inserted, so this nut gets "
                       "no insert command. Rotate the part on the plate or fix the pocket in CAD.")
    if cls == ROLLED:
        return finding("W_ROLLED", f"{label}: nut lies on its side rolled {roll:.1f}° about "
                       "its thread axis. It must stand on a flat (0°) or on a corner "
                       "(45°), so this nut gets no insert command.")
    return None


def check(label: str, cls: str, nut: NutType, m: Measurement, settings: Settings) -> list[Finding]:
    """Findings for one placeable nut (FLAT, EDGE or CORNER)."""
    out: list[Finding | None] = []
    if not nut.class_enabled(cls):
        out.append(finding("E_CLASS_DISABLED", f"{label}: this nut is {cls}, and that class is "
                           f"switched off for {nut.key} in the nut library. Change the design, "
                           "or enable the class once your tool can place it."))
    out += [finding(code, f"{label}: {text}.") for code, text in m.issues]

    if cls == FLAT:
        spec = nut.flat
        for width in m.widths:
            out.append(range_finding(label, "E_WIDTH", "pocket width", width, *spec.width))
        if m.depth is not None:
            out.append(range_finding(label, "E_DEPTH", "pocket depth", m.depth, *spec.depth))
    elif cls == EDGE:
        spec = nut.edge
        if m.thickness is not None:
            out.append(range_finding(label, "E_THICKNESS", "slot thickness", m.thickness,
                                     *spec.thickness))
        for width in m.widths:
            out.append(range_finding(label, "E_WIDTH", "slot width", width, *spec.width))
        if m.depth is not None:
            out.append(minimum_finding(label, "E_DEPTH", "slot height", m.depth,
                                       spec.height_min))
    elif cls == CORNER:
        spec = nut.corner
        if m.thickness is not None:
            out.append(range_finding(label, "E_THICKNESS", "slot thickness", m.thickness,
                                     *spec.thickness))
        for width in m.widths:
            out.append(range_finding(label, "E_WIDTH", "slot opening", width, *spec.opening))
        for gap in m.seat_gaps:
            if gap > spec.seat_gap_max + CHECK_EPS:
                out.append(finding("E_SEAT", f"{label}: seat gap {gap:.2f} mm between a lower "
                                   f"flat and its wall, allowed 0.00–{spec.seat_gap_max:.2f} "
                                   "mm. Move the V walls in CAD and re-export."))
        if m.depth is not None:
            out.append(minimum_finding(label, "E_DEPTH", "slot height", m.depth,
                                       spec.height_min))

    if m.roof_span is not None and m.roof_span > nut.max_roof_span + CHECK_EPS:
        out.append(finding("W_ROOF_SPAN", f"{label}: the roof bridges {m.roof_span:.2f} mm, more "
                           f"than the {nut.max_roof_span:.2f} mm this nut type allows."))
    if m.roof_z is not None and m.z_high is not None:
        below = m.roof_z - m.z_high
        if below > nut.tool_reach + CHECK_EPS:
            out.append(finding("W_REACH", f"{label}: the seated nut's top is {below:.2f} mm below "
                               f"the insert layer, and the tool reaches {nut.tool_reach:.2f} mm."))
    if m.displacement is not None:
        off = float(np.hypot(m.displacement[0], m.displacement[1]))
        if off > OFF_CENTRE:
            out.append(finding("N_OFF_CENTRE", f"{label}: nut body is {off:.2f} mm from the "
                               "pocket centre. The pocket centre is used."))
    return [f for f in out if f is not None]
