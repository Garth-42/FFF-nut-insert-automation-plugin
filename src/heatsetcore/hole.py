"""Measure the hole an insert sits in: axis, diameter, rim, bottom, wall, surface, open end.

docs/heatset-plan.md, "Detection" steps 2 to 8. Everything is in bed coordinates. The host
is the triangle corners (T, 3, 3) of the parts that print; walls are found with rays
(nutcore.rays), so the host need not be watertight. Distances along the axis ("s") are
measured from the middle of the insert body, positive upward.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from nutcore.rays import GAP_BIN, cast, cast_fan

from .insert import InsertFrame

HOLE_RAYS = 16          # radial rays per height for the hole wall
HOLE_HEIGHTS = 5        # heights along the insert
WALL_RAYS = 36          # radial rays per height for the wall: a flat outside face between
                        # two rays reads at most (r + wall) * (1 / cos 5° - 1) too thick
WALK_RAYS = 8           # radial rays per height in the rim and bottom walks
WALK_STEP = 0.5         # mm, coarse step of the walks, then refined:
REFINE = 6              # rounds, each trying
REFINE_POINTS = 15      # this many points between the last good and the first bad one:
                        # 0.5 mm / 16**6, so an exact-size hole still passes CHECK_EPS
WALK_BEYOND = 10.0      # mm the walks go past the body's ends
RIM_FLARE = 1.0         # mm a chamfer may widen the hole and still belong to it
HOLE_TOL = 0.2          # mm change of radius that ends the hole going down
DISC = 0.6              # share of the hole radius used by the rays along the axis
COVER_GAP = 0.2         # mm: a ceiling more than this above the rim is a lid
UP_REACH = 50.0         # mm above the rim within which a lid counts
SURFACE_BAND = 1.0      # mm: surface points this close to the rim height count
REACH_FACTOR = 3.0      # a wall may be this many insert diameters away
_ANGLE0 = 0.1234        # rad: ray directions start off the facet corners of round holes

UPRIGHT, INVERTED = "UPRIGHT", "INVERTED"


@dataclass
class HoleMeasure:
    issues: list = field(default_factory=list)   # (code, text): errors, no insert
    notes: list = field(default_factory=list)    # (code, text): notes and warnings
    cls: str | None = None                       # UPRIGHT or INVERTED
    centre: np.ndarray | None = None             # the hole axis at the body's middle
    diameter: float | None = None
    offset: float = 0.0                          # body axis to hole axis, in the plane
    s_rim: float | None = None                   # where the wall ends going up
    s_bottom: float | None = None                # where the hole ends going down
    through: bool = False                        # it opens at the bottom too
    wall: float | None = None                    # thinnest wall around the hole
    surface_tilt: float | None = None            # degrees from level, around the rim

    def at(self, axis: np.ndarray, s: float) -> np.ndarray:
        return self.centre + axis * s

    @property
    def depth(self) -> float | None:
        if self.s_rim is None or self.s_bottom is None:
            return None
        return self.s_rim - self.s_bottom


def _plane(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    helper = np.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(axis, helper)
    u /= np.linalg.norm(u)
    return u, np.cross(axis, u)


def _directions(u, v, n: int) -> np.ndarray:
    angles = _ANGLE0 + 2 * np.pi * np.arange(n) / n
    return np.cos(angles)[:, None] * u + np.sin(angles)[:, None] * v


def _nearby(host: np.ndarray, centre: np.ndarray, reach: float, length: float) -> np.ndarray:
    if len(host) == 0:
        return host
    lo, hi = host.min(axis=1), host.max(axis=1)
    box_lo = centre - np.array([reach, reach, length + WALK_BEYOND + reach])
    box_hi = centre + np.array([reach, reach, UP_REACH + length])
    return host[np.all((hi >= box_lo) & (lo <= box_hi), axis=1)]


def _near_axis(tris: np.ndarray, p0: np.ndarray, p1: np.ndarray, radius: float) -> np.ndarray:
    """The triangles that can be hit within radius of the segment p0-p1 (box test)."""
    if len(tris) == 0:
        return tris
    lo, hi = np.minimum(p0, p1) - radius, np.maximum(p0, p1) + radius
    return tris[np.all((tris.max(axis=1) >= lo) & (tris.min(axis=1) <= hi), axis=1)]


def _radial(tris, centre, axis, s, dirs, reach) -> np.ndarray:
    """Distance along each radial direction from points on the axis: (len(s), len(dirs))."""
    t = cast_fan(centre, axis, s, dirs, tris)
    return np.where(t <= reach, t, np.inf)


def _fit_circle(points: np.ndarray) -> tuple[np.ndarray, float]:
    """Least-squares (Kasa) circle through 2-D points: centre, radius."""
    x, y = points[:, 0], points[:, 1]
    a = np.column_stack([x, y, np.ones_like(x)])
    d, e, f = np.linalg.lstsq(a, -(x * x + y * y), rcond=None)[0]
    centre = np.array([-d / 2, -e / 2])
    return centre, float(np.sqrt(max(centre @ centre - f, 0.0)))


def _heading(d: np.ndarray) -> str:
    return f"heading {np.degrees(np.arctan2(d[1], d[0])) % 360:.0f}°"


def _walk(tris, centre, axis, dirs, sign: float, limit: float, low: float,
          high: float) -> float:
    """The farthest s (in the direction of sign) up to which every radial ray sees a wall
    at a distance between low and high."""
    tris = _near_axis(tris, centre, centre + sign * (limit + WALK_STEP) * axis, high)

    def present(values) -> np.ndarray:
        t = cast_fan(centre, axis, values, dirs, tris)
        return np.all((t >= low) & (t <= high), axis=1)

    values = sign * np.arange(0.0, limit + WALK_STEP, WALK_STEP)
    ok = present(values)
    if not ok[0]:
        return 0.0
    if ok.all():
        return float(values[-1])
    first = int(np.argmin(ok))
    lo, hi = values[first - 1], values[first]
    for _ in range(REFINE):
        points = lo + (hi - lo) * np.arange(1, REFINE_POINTS + 1) / (REFINE_POINTS + 1)
        ok = present(points)
        if ok.all():
            lo = points[-1]
            continue
        first = int(np.argmin(ok))
        hi = points[first]
        if first:
            lo = points[first - 1]
    return float(lo)


def measure_hole(frame: InsertFrame, host: np.ndarray, prof: dict) -> HoleMeasure:
    """Find the hole around an insert body whose axis is near vertical, and measure it."""
    m = HoleMeasure()
    a, c, length = frame.axis, frame.centre, frame.length
    u, v = _plane(a)
    reach = REACH_FACTOR * prof["insert_od"]
    tris = _nearby(host, c, reach, length)
    s = np.linspace(-0.4 * length, 0.4 * length, HOLE_HEIGHTS)
    dirs = _directions(u, v, HOLE_RAYS)

    # Hole axis and diameter: fit a circle to the wall hits, then again from its centre.
    origin, offset2d, radius = c, np.zeros(2), 0.0
    for _ in range(2):
        dist = _radial(tris, origin, a, s, dirs, reach)
        missing = ~np.isfinite(dist).any(axis=0)
        if missing.any():
            m.issues.append(("E_NO_POCKET", f"the hole is open towards "
                             f"{_heading(dirs[missing][0])}: no wall within {reach:.1f} mm. "
                             "The insert body must sit in a hole of the same object"))
            return m
        rel = origin - c
        hits = rel[None, None, :] + dist[:, :, None] * dirs[None, :, :]
        finite = np.isfinite(dist)
        points = np.column_stack([hits[finite] @ u, hits[finite] @ v])
        offset2d, radius = _fit_circle(points)
        origin = c + offset2d[0] * u + offset2d[1] * v
    m.centre, m.diameter = origin, 2 * radius
    m.offset = float(np.hypot(*offset2d))

    # Wall: past the hole's wall, on outward to the next surface.
    out = _directions(u, v, WALL_RAYS)
    first = cast_fan(origin, a, s, out, tris)
    second = cast_fan(origin, a, s, out, tris, beyond=first + 1e-4)
    walls = (second - first)[np.isfinite(second) & (first <= reach)]
    m.wall = float(walls.min()) if len(walls) else None

    # Rim and bottom: walk up and down from the middle of the insert.
    walk = _directions(u, v, WALK_RAYS)
    limit = length / 2 + WALK_BEYOND
    m.s_rim = _walk(tris, origin, a, walk, 1.0, limit, 0.0, radius + RIM_FLARE)
    m.s_bottom = _walk(tris, origin, a, walk, -1.0, limit, radius - HOLE_TOL, radius + HOLE_TOL)
    below = _radial(tris, origin, a, [m.s_bottom - 0.3], walk, reach)
    m.through = not np.isfinite(below).any()

    # Which way the hole opens: rays along the axis from a disc inside it.
    ring = DISC * radius * _directions(u, v, 6)
    disc = origin + np.vstack([np.zeros(3), ring])
    up = cast(disc, a, tris)
    up = np.where(up <= m.s_rim + UP_REACH, up, np.inf)
    blocked = up[np.isfinite(up)]
    if len(blocked) == 0:
        m.cls = UPRIGHT
    elif (blocked < m.s_rim - GAP_BIN).any():
        z = float(m.at(a, float(blocked.min()))[2])
        m.issues.append(("E_DROP_PATH", f"something narrows the hole above the insert at "
                         f"Z {z:.2f}, so the insert cannot be pressed in from above. Clear the "
                         "hole in CAD and re-export"))
        return m
    elif len(blocked) == len(up) and blocked.max() <= m.s_rim + COVER_GAP:
        down = cast(disc, -a, tris)
        if np.isfinite(np.where(down <= reach + limit, down, np.inf)).any():
            m.issues.append(("E_DROP_PATH", "the hole is closed at both ends, so the insert "
                             "can be neither pressed in nor fitted by hand. Open the hole in "
                             "CAD and re-export"))
            return m
        m.cls = INVERTED
        return m
    else:
        m.cls = UPRIGHT
        gap = float(blocked.min() - m.s_rim)
        m.notes.append(("N_COVERED", f"something is modelled over the hole {gap:.2f} mm above "
                        "its rim. With timing after_layer the insert goes in first and is "
                        "printed over afterwards; with end_of_print the tool cannot reach it"))

    # Surface: points around the rim, at most the pad's radius out, must lie level.
    rim_z = float(m.at(a, m.s_rim)[2])
    radii = np.arange(radius + 0.75, max(radius + 0.75, prof["pad_d"] / 2 - 0.25) + 1e-9, 1.0)
    angles = _ANGLE0 + 2 * np.pi * np.arange(12) / 12
    xy = np.array([[origin[0] + r_ * np.cos(t_), origin[1] + r_ * np.sin(t_)]
                   for r_ in radii for t_ in angles])
    starts = np.column_stack([xy, np.full(len(xy), rim_z + SURFACE_BAND)])
    t = cast(starts, np.array([0.0, 0.0, -1.0]), tris)
    z = rim_z + SURFACE_BAND - t
    near = np.isfinite(t) & (np.abs(z - rim_z) <= SURFACE_BAND)
    if near.sum() >= 6:
        fit = np.linalg.lstsq(np.column_stack([xy[near], np.ones(near.sum())]), z[near],
                              rcond=None)[0]
        m.surface_tilt = float(np.degrees(np.arctan(np.hypot(fit[0], fit[1]))))
    return m
