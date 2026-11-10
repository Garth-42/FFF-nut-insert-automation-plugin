"""Measure the pocket around one nut: walls, seat, centring, drop path and rim.

Everything here is in bed coordinates. The host is given as triangle corners
(T, 3, 3); walls are found with rays, so the host need not be watertight.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .frame import CORNER, EDGE, FLAT, NutFrame, Z
from .rays import GAP_BIN, GAP_EPS, RAY_GRID, RAY_INSET, cast, face_grid, robust_nearest

RAY_REACH_FACTOR = 3.0   # a wall may be this many widths across flats away
ROOF_AGREE = 0.5         # share of drop rays that must agree on the roof (see DECISIONS.md)
RIM_STEP = 0.05          # mm, upward walk for open-top pockets
RIM_MAX = 50.0           # mm, stop the walk here
OFF_CENTRE = 0.1         # mm, off-centre note


@dataclass
class Measurement:
    """What the rays found. `issues` are (code, text) pairs; the checker adds the nut label."""

    issues: list[tuple[str, str]] = field(default_factory=list)
    placement: np.ndarray | None = None      # centre of the seated, centred nut
    displacement: np.ndarray | None = None   # placement minus modelled centre
    z_low: float | None = None
    z_high: float | None = None
    roof_z: float | None = None
    rim_z: float | None = None
    widths: list[float] = field(default_factory=list)  # FLAT: two. EDGE: one. CORNER: opening
    thickness: float | None = None           # EDGE and CORNER: slot size along the thread axis
    depth: float | None = None               # floor (or lowest corner) to roof or rim
    seat_gaps: list[float] = field(default_factory=list)
    roof_span: float | None = None
    box: dict | None = None                  # the measured pocket as an oriented box


def nearby_triangles(corners: np.ndarray, centre: np.ndarray, reach: float) -> np.ndarray:
    """Host triangles whose bounding box comes within reach of the nut.

    The box is taller upward so the rim walk of an open-top pocket still sees the walls.
    """
    if len(corners) == 0:
        return corners
    lo, hi = corners.min(axis=1), corners.max(axis=1)
    box_lo = centre - reach
    box_hi = centre + reach + np.array([0.0, 0.0, RIM_MAX])
    return corners[np.all((hi >= box_lo) & (lo <= box_hi), axis=1)]


def _side(n: np.ndarray) -> str:
    """Name a direction for a message."""
    if abs(n[2]) > 0.9:
        return "above" if n[2] > 0 else "below"
    return f"towards X{n[0]:+.2f} Y{n[1]:+.2f}"


def _gap(tris, centre, n, h, p, hp, q, hq, reach) -> float | None:
    """Gap between a nut face and the wall it sees, or None when that side is open."""
    origins = face_grid(centre, p, hp, q, hq)
    t = cast(origins, n, tris)
    return robust_nearest(t[t <= h + reach] - h, len(origins))


def measure(frame: NutFrame, cls: str, host: np.ndarray, across_flats: float) -> Measurement:
    """Settle and centre the nut in its pocket and measure the pocket."""
    m = Measurement()
    a, u, v, c = frame.a, frame.u, frame.v, frame.centre
    ha, hu, hv = frame.ha, frame.hu, frame.hv
    reach = RAY_REACH_FACTOR * across_flats
    tris = nearby_triangles(host, c, reach)

    # The six faces: (normal, half extent along it, in-plane axes and their half extents).
    faces = []
    for n, h, p, hp, q, hq in ((a, ha, u, hu, v, hv), (u, hu, a, ha, v, hv),
                               (v, hv, a, ha, u, hu)):
        faces.append((n, h, p, hp, q, hq))
        faces.append((-n, h, p, hp, q, hq))

    raw = [_gap(tris, c, *face, reach) for face in faces]
    if all(g is None for g in raw):
        m.issues.append(("E_NO_POCKET", f"no wall within {reach:.1f} mm on any side. "
                         "The nut body must sit inside a pocket of the same object"))
        return m

    # --- Seat: settle the nut onto the faces that point down. -------------------------------
    seat = [(face, g) for face, g in zip(faces, raw, strict=True) if face[0][2] <= -0.5]
    if any(g is None for _, g in seat):
        m.issues.append(("E_SEAT", "a face that points down sees no floor or wall to rest on. "
                         "Close the pocket under the nut in CAD and re-export"))
        return m
    gaps = np.array([g for _, g in seat])
    m.seat_gaps = gaps.tolist()
    if gaps.min() < -GAP_EPS:
        m.issues.append(("E_INTERFERENCE", f"the nut body cuts {-gaps.min():.2f} mm into its "
                         "seat. Move the body or the pocket floor in CAD and re-export"))
    normals = np.array([face[0] for face, _ in seat])
    d = np.linalg.pinv(normals) @ gaps          # solves n_f . d = gap_f, shortest d
    settled = c + d

    # --- Sideways: measure and centre between each pair of walls. ---------------------------
    if cls == FLAT:
        pairs = [(u, hu, a, ha, v, hv, "width"), (v, hv, a, ha, u, hu, "width")]
    elif cls == EDGE:
        pairs = [(a, ha, u, hu, v, hv, "thickness"), (v, hv, a, ha, u, hu, "width")]
    else:
        pairs = [(a, ha, u, hu, v, hv, "thickness")]
    complete = True
    for n, h, p, hp, q, hq, kind in pairs:
        g_plus = _gap(tris, settled, n, h, p, hp, q, hq, reach)
        g_minus = _gap(tris, settled, -n, h, p, hp, q, hq, reach)
        if not _pair_ok(m, n, g_plus, g_minus, reach):
            complete = False
            continue
        size = 2 * h + g_plus + g_minus
        d = d + n * (g_plus - g_minus) / 2
        if kind == "thickness":
            m.thickness = size
        else:
            m.widths.append(size)

    h_dir = np.cross(a, Z)
    h_dir = h_dir / max(np.linalg.norm(h_dir), 1e-12)
    corner_r = float(np.hypot(hu, hv))
    opening_shift = 0.0
    if cls == CORNER and complete:
        # Opening: horizontal rays through the nut's two side corner edges.
        centre_line = c + d + np.linspace(-RAY_INSET, RAY_INSET, RAY_GRID)[:, None] * ha * a
        side_gaps = []
        for sign in (1.0, -1.0):
            t = cast(centre_line, sign * h_dir, tris)
            side_gaps.append(robust_nearest(t[t <= corner_r + reach] - corner_r, RAY_GRID))
        if _pair_ok(m, h_dir, side_gaps[0], side_gaps[1], reach):
            m.widths.append(2 * corner_r + side_gaps[0] + side_gaps[1])
            opening_shift = (side_gaps[0] - side_gaps[1]) / 2
        else:
            complete = False
    if not complete:
        return m

    placement = c + d
    r = {FLAT: ha, EDGE: hu, CORNER: corner_r}[cls]     # vertical half extent
    m.placement, m.displacement = placement, d
    m.z_low, m.z_high = float(placement[2] - r), float(placement[2] + r)

    # The nut's horizontal mid-plane: (axis, half extent) twice. Every point on it is
    # inside the nut, so rays that start there cannot begin behind a wall.
    if cls == FLAT:
        plane = (u, hu, v, hv)
    elif cls == EDGE:
        plane = (a, ha, v, hv)
    else:
        plane = (a, ha, h_dir, corner_r)

    # --- Drop path: straight up from the seated nut. ----------------------------------------
    origins = face_grid(placement, *plane)
    t = cast(origins, Z, tris)
    hits = placement[2] + t[t <= r + reach]
    top = None
    if len(hits) == 0:
        m.rim_z = _rim(tris, placement, [(plane[0], plane[1]), (plane[2], plane[3])], reach)
        top = m.rim_z
    else:
        roof = robust_nearest(hits, len(origins), agree=ROOF_AGREE)
        if roof is None or hits.min() < roof - GAP_BIN:
            m.issues.append(("E_DROP_PATH", "something overhangs part of the pocket at "
                             f"Z {hits.min():.2f}, so the nut cannot drop straight onto its "
                             "seat. Clear the space above the pocket in CAD and re-export"))
        if roof is not None:
            m.roof_z = top = roof
            if roof < m.z_high - GAP_EPS:
                m.issues.append(("E_INTERFERENCE", f"the nut body cuts {m.z_high - roof:.2f} "
                                 "mm into the pocket roof. Raise the roof in CAD and re-export"))

    # --- Derived values. --------------------------------------------------------------------
    if top is not None:
        m.depth = float(top - m.z_low)
    if m.roof_z is not None:
        m.roof_span = float(min(m.widths + ([m.thickness] if m.thickness else [])))
    height = m.depth if m.depth and m.depth > 0 else 2 * r
    half = [(m.thickness if cls != FLAT else m.widths[0]) / 2,
            m.widths[-1] / 2, height / 2]
    box_centre = placement + opening_shift * h_dir
    box_centre[2] = m.z_low + height / 2
    m.box = {"centre": box_centre.tolist(),
             "axes": [plane[0].tolist(), plane[2].tolist(), Z.tolist()],
             "half": [float(x) for x in half]}
    return m


def _pair_ok(m: Measurement, n, g_plus, g_minus, reach) -> bool:
    """Record open sides and interference for one pair of walls. True when both walls exist."""
    ok = True
    for sign, g in ((1.0, g_plus), (-1.0, g_minus)):
        if g is None:
            m.issues.append(("E_NO_POCKET", f"the pocket is open {_side(sign * n)}: no wall "
                             f"within {reach:.1f} mm. Close that side in CAD and re-export"))
            ok = False
        elif g < -GAP_EPS:
            m.issues.append(("E_INTERFERENCE", f"the nut body cuts {-g:.2f} mm into the wall "
                             f"{_side(sign * n)}. Widen the pocket in CAD and re-export"))
    return ok


def _rim(tris, placement, pairs, reach) -> float:
    """Height of the rim of an open-top pocket.

    Walk upward from the nut's centre, one horizontal ray per side. The rim is
    the last height at which every side still sees its wall.
    """
    def seen(heights: np.ndarray) -> np.ndarray:
        origins = np.column_stack([np.full(len(heights), placement[0]),
                                   np.full(len(heights), placement[1]), heights])
        ok = np.ones(len(heights), dtype=bool)
        for n, h in pairs:
            for sign in (1.0, -1.0):
                ok &= cast(origins, sign * n, tris) <= h + reach
        return ok

    chunk = 100
    total = int(RIM_MAX / RIM_STEP)
    last_seen = None
    for start in range(0, total + 1, chunk):
        heights = placement[2] + np.arange(start, min(start + chunk, total + 1)) * RIM_STEP
        ok = seen(heights)
        if ok.all():
            last_seen = heights[-1]
            continue
        first_bad = int(np.argmin(ok))
        lo = heights[first_bad - 1] if first_bad > 0 else last_seen
        if lo is None:
            return float(placement[2])       # no walls even at the nut's centre
        hi = heights[first_bad]
        for _ in range(40):                  # refine between the two steps
            mid = (lo + hi) / 2
            if seen(np.array([mid]))[0]:
                lo = mid
            else:
                hi = mid
        return float(lo)
    return float(last_seen)
