"""The nut frame (three axes, centre, extents) and the orientation class."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .faces import FlatFace

FLAT, EDGE, CORNER, TILTED, ROLLED = "FLAT", "EDGE", "CORNER", "TILTED", "ROLLED"
PLACEABLE = (FLAT, EDGE, CORNER)
Z = np.array([0.0, 0.0, 1.0])


class BodySizeError(ValueError):
    """The body does not measure like the library nut. Reported as E_BODY_SIZE."""

    def __init__(self, message: str, measured=None):
        super().__init__(message)
        self.measured = measured


@dataclass(frozen=True)
class NutFrame:
    a: np.ndarray       # thread axis, unit vector
    u: np.ndarray       # across the flats
    v: np.ndarray       # across the flats
    centre: np.ndarray  # middle of the three extents
    ha: float           # half thickness, as measured
    hu: float           # half width across flats, as measured
    hv: float

    @property
    def body_size(self) -> tuple[float, float, float]:
        return (2 * self.hu, 2 * self.hv, 2 * self.ha)


@dataclass(frozen=True)
class Orientation:
    cls: str
    frame: NutFrame          # the frame with its signs fixed by rule
    tilt_deg: float          # thread axis from Z, 0..90
    roll_deg: float | None   # on-edge only: flats from vertical, 0..45
    yaw_deg: float | None    # FLAT: yaw of the flats 0..90. On edge: heading 0..180


def nut_frame(vertices: np.ndarray, faces: list[FlatFace], across_flats: float,
              thickness: float, axis_tol_deg: float, body_tol: float) -> NutFrame:
    """Find the nut's axes from its flat faces and check its size against the library."""
    # Merge faces that point the same or the opposite way into directions.
    cos_same = np.cos(np.radians(axis_tol_deg))
    directions: list[list] = []  # [unit vector, total area]
    for face in faces:
        for entry in directions:
            if abs(entry[0] @ face.normal) >= cos_same:
                entry[1] += face.area
                break
        else:
            directions.append([face.normal, face.area])
    directions.sort(key=lambda entry: -entry[1])

    # The three largest directions that are perpendicular to each other.
    sin_tol = np.sin(np.radians(axis_tol_deg))
    axes: list[np.ndarray] = []
    for normal, _ in directions:
        if all(abs(normal @ chosen) <= sin_tol for chosen in axes):
            axes.append(normal)
        if len(axes) == 3:
            break
    if len(axes) < 3:
        raise BodySizeError("the body is not a box with three perpendicular pairs of faces")

    proj = vertices @ np.array(axes).T          # (N, 3)
    lo, hi = proj.min(axis=0), proj.max(axis=0)
    extent = hi - lo
    centre = ((lo + hi) / 2) @ np.array(axes)   # exact for perpendicular axes
    for i in range(3):
        j, k = (i + 1) % 3, (i + 2) % 3
        if (abs(extent[i] - thickness) <= body_tol and abs(extent[j] - across_flats) <= body_tol
                and abs(extent[k] - across_flats) <= body_tol):
            return NutFrame(a=axes[i], u=axes[j], v=axes[k], centre=centre,
                            ha=extent[i] / 2, hu=extent[j] / 2, hv=extent[k] / 2)
    raise BodySizeError("the body does not measure like the library nut",
                        measured=tuple(sorted(extent.tolist(), reverse=True)))


def _snap(angle: float, period: float) -> float:
    """angle mod period, with values a hair below the period folded to 0."""
    angle = angle % period
    return 0.0 if period - angle < 1e-7 else angle


def classify(frame: NutFrame, axis_tol_deg: float) -> Orientation:
    """Classify the nut from its axes in bed coordinates and fix the axis signs by rule."""
    a, u, v = frame.a, frame.u, frame.v
    tilt = float(np.degrees(np.arccos(min(1.0, abs(a[2])))))

    if tilt <= axis_tol_deg:
        # FLAT. a points up, u is the flat direction with yaw in 0..90.
        a = a if a[2] > 0 else -a
        yaw = _snap(np.degrees(np.arctan2(u[1], u[0])), 90.0)
        target = np.array([np.cos(np.radians(yaw)), np.sin(np.radians(yaw)), 0.0])
        options = [(u, frame.hu, v, frame.hv), (-u, frame.hu, v, frame.hv),
                   (v, frame.hv, u, frame.hu), (-v, frame.hv, u, frame.hu)]
        u2, hu2, other, hv2 = max(options, key=lambda option: option[0] @ target)
        v2 = other if np.cross(a, u2) @ other > 0 else -other
        fixed = replace(frame, a=a, u=u2, v=v2, hu=hu2, hv=hv2)
        return Orientation(FLAT, fixed, tilt, None, float(yaw))

    if abs(90.0 - tilt) <= axis_tol_deg:
        # On edge. a is horizontal with heading in 0..180.
        heading = _snap(np.degrees(np.arctan2(a[1], a[0])), 180.0)
        target = np.array([np.cos(np.radians(heading)), np.sin(np.radians(heading)), 0.0])
        a = a if a @ target > 0 else -a
        roll = float(np.degrees(np.arccos(min(1.0, max(abs(u[2]), abs(v[2]))))))
        u = u if u[2] >= 0 else -u
        v = v if v[2] >= 0 else -v
        hu, hv = frame.hu, frame.hv
        if roll <= axis_tol_deg:
            cls = EDGE
            if abs(v[2]) > abs(u[2]):          # u is the vertical one
                u, v, hu, hv = v, u, hv, hu
            v = v if np.cross(a, u) @ v > 0 else -v
        else:
            cls = CORNER if abs(45.0 - roll) <= axis_tol_deg else ROLLED
            if np.cross(a, u) @ v < 0:         # keep (a, u, v) right-handed
                u, v, hu, hv = v, u, hv, hu
        fixed = replace(frame, a=a, u=u, v=v, hu=hu, hv=hv)
        return Orientation(cls, fixed, tilt, roll, float(heading))

    a = a if a[2] > 0 else -a
    return Orientation(TILTED, replace(frame, a=a), tilt, None, None)
