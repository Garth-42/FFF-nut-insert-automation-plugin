"""Per-pocket G-code analysis: local layers, snapping to the print, and the pocket proof."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..report import Finding, NutRecord, finding
from .parser import Parsed

PROOF_RING = 2.0    # mm, band around the footprint that defines local layers
PROOF_INSET = 0.2   # mm, shrink of the footprint for the empty-pocket test
Z_EPS = 0.001       # mm, equality of heights


@dataclass
class PocketPlan:
    """What the G-code says about one nut's pocket."""

    findings: list[Finding] = field(default_factory=list)
    on_plate: bool = True
    layer: int | None = None        # insert layer, counted at the pocket from 1
    layer_z: float | None = None    # top of the insert layer
    z_low: float | None = None      # lowest point of the seated nut, as printed
    z_high: float | None = None
    line: int | None = None         # index of the line the block is written after

    @property
    def z(self) -> float:
        return (self.z_low + self.z_high) / 2

    def has_error(self) -> bool:
        return any(f.level == "error" for f in self.findings)


def crosses_rect(seg: np.ndarray, centre, e1, e2, h1: float, h2: float) -> np.ndarray:
    """Which segments (K, 6) touch an oriented rectangle in XY. Returns a (K,) mask."""
    if len(seg) == 0 or h1 <= 0 or h2 <= 0:
        return np.zeros(len(seg), dtype=bool)
    c, e1, e2 = np.asarray(centre)[:2], np.asarray(e1)[:2], np.asarray(e2)[:2]
    p0, p1 = seg[:, 0:2] - c, seg[:, 3:5] - c
    t_in = np.zeros(len(seg))
    t_out = np.ones(len(seg))
    ok = np.ones(len(seg), dtype=bool)
    for axis, half in ((e1, h1), (e2, h2)):          # clip against two slabs
        a = p0 @ axis
        d = (p1 @ axis) - a
        parallel = np.abs(d) < 1e-12
        ok &= ~parallel | (np.abs(a) <= half)
        safe = np.where(parallel, 1.0, d)
        t1, t2 = (-half - a) / safe, (half - a) / safe
        t_in = np.where(parallel, t_in, np.maximum(t_in, np.minimum(t1, t2)))
        t_out = np.where(parallel, t_out, np.minimum(t_out, np.maximum(t1, t2)))
    return ok & (t_in <= t_out)


def plan_pocket(parsed: Parsed, record: NutRecord, min_top_clearance: float,
                tool_reach: float) -> PocketPlan:
    """Find the layers around one pocket, prove it is empty and pick the insert layer."""
    plan = PocketPlan()
    label = record.label
    centre, (e1, e2, _), (h1, h2, _) = record.box["centre"], record.box["axes"], \
        record.box["half"]
    seg, seg_line = parsed.extruding
    local = crosses_rect(seg, centre, e1, e2, h1 + PROOF_RING, h2 + PROOF_RING)
    seg, seg_line = seg[local], seg_line[local]
    floor = record.z_low
    top_limit = record.roof_z if record.roof_z is not None else record.rim_z

    def not_on_plate():
        plan.on_plate = False
        plan.findings.append(finding("N_NOT_ON_PLATE", f"{label}: nothing is printed around "
                                     "this pocket in this file, so the nut is skipped."))
        return plan

    if len(seg) == 0:
        return not_on_plate()
    if np.any(np.abs(seg[:, 5] - seg[:, 2]) > Z_EPS):
        plan.findings.append(finding("E_NO_LAYERS", f"{label}: extrusion changes height inside "
                                     "a move near this pocket (spiral or non-planar printing), "
                                     "so there are no layers to insert between."))
        return plan

    z_keys = np.round(seg[:, 5] / Z_EPS).astype(np.int64)
    unique = np.unique(z_keys)
    tops = unique * Z_EPS
    bottoms = np.concatenate([[0.0], tops[:-1]])
    mids = (tops + bottoms) / 2
    is_open = (mids > floor + Z_EPS) & (mids < top_limit - Z_EPS)
    if not is_open.any():
        return not_on_plate()
    first, last = np.flatnonzero(is_open)[[0, -1]]

    # Print order: heights near the pocket must not fall back by more than one layer.
    layer_of = np.searchsorted(unique, z_keys)
    if np.any(layer_of < np.maximum.accumulate(layer_of) - 1):
        plan.findings.append(_print_order(label))
        return plan

    # Pocket proof: in every open layer nothing may be extruded inside the footprint.
    for i in np.flatnonzero(is_open):
        in_layer = seg[layer_of == i]
        half2 = h2
        if record.cls == "CORNER":
            half2 = min(h2, mids[i] - floor)   # the V is narrower near its bottom
        if crosses_rect(in_layer, centre, e1, e2, h1 - PROOF_INSET, half2 - PROOF_INSET).any():
            plan.findings.append(finding(
                "E_POCKET_NOT_EMPTY", f"{label}: plastic is printed inside the pocket in the "
                f"layer at Z {tops[i]:.3f}. The nut body is still a printing part (select it, "
                "right-click, Change type, Modifier), or there is support in the pocket."))
            return plan

    # Snap to the print: the printed pocket can differ from the model by half a layer.
    if record.cls == "CORNER":
        plan.z_low, plan.z_high = record.z_low, record.z_high
    else:
        plan.z_low = float(bottoms[first])
        plan.z_high = plan.z_low + (record.z_high - record.z_low)
    if record.roof_z is not None:
        printed_roof = float(tops[last])
        if printed_roof - plan.z_high < min_top_clearance - Z_EPS:
            plan.findings.append(finding(
                "E_PRINTED_DEPTH", f"{label}: as printed the pocket runs from Z {plan.z_low:.3f} "
                f"to {printed_roof:.3f}, which leaves {printed_roof - plan.z_high:.3f} mm above "
                f"the nut; {min_top_clearance:.3f} mm is needed. Make the pocket deeper in CAD, "
                "or align its floor and roof with the layer heights."))
            return plan
        insert = int(last)
    else:
        clear = np.flatnonzero(tops >= plan.z_high + min_top_clearance - Z_EPS)
        insert = int(clear[0]) if len(clear) else len(tops) - 1
    plan.layer, plan.layer_z = insert + 1, float(tops[insert])

    # Insertion point: after the last extruding move in the file at or below the layer top.
    all_seg, all_line = parsed.extruding
    at_or_below = all_line[all_seg[:, 5] <= plan.layer_z + Z_EPS]
    plan.line = int(at_or_below.max())
    if np.any(seg_line[layer_of > insert] <= plan.line):
        plan.findings.append(_print_order(label))   # the pocket is closed before that point
        return plan

    if plan.layer_z - plan.z_high > tool_reach + Z_EPS:
        plan.findings.append(finding(
            "W_REACH", f"{label}: as printed the nut's top is {plan.layer_z - plan.z_high:.2f} "
            f"mm below the insert layer, and the tool reaches {tool_reach:.2f} mm."))
    return plan


def _print_order(label: str) -> Finding:
    return finding("E_PRINT_ORDER", f"{label}: the print does not go up layer by layer at this "
                   "pocket. Set the print sequence to By layer.")
