"""The insert frame: axis, centre, length and diameter of a heat-set insert body.

docs/heatset-plan.md, "Detection" step 1. A nut's frame comes from nutcore.faces, which
seeds directions from the largest triangles and stops after 40; a cylinder's side
triangles are larger than its cap triangles, so that never finds the caps. Here triangle
normals are binned by direction instead, each direction folded together with its
opposite, and the areas summed: the end caps are flat, so their pair normally has the
largest total. Directions are tried in that order and the first along which the body
measures the profile's length, with the profile's diameter around it, wins.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from nutcore.mesh import normals_and_areas

BIN = 1e-3          # direction bins: unit-normal components rounded to this
CANDIDATES = 8      # directions tried, largest total area first
MIN_AREA = 1e-9     # mm², smaller triangles are dropped


class BodySizeError(ValueError):
    """The body does not measure like the profile's insert. Reported as E_BODY_SIZE."""

    def __init__(self, message: str, measured=None):
        super().__init__(message)
        self.measured = measured       # (length, diameter) of the best candidate


@dataclass(frozen=True)
class InsertFrame:
    axis: np.ndarray      # unit vector, pointing up (z >= 0)
    centre: np.ndarray    # the middle of the body, on its axis
    length: float         # extent along the axis, as measured
    diameter: float       # twice the largest distance of a vertex from the axis

    @property
    def tilt_deg(self) -> float:
        return float(np.degrees(np.arccos(min(1.0, abs(self.axis[2])))))

    @property
    def top(self) -> np.ndarray:
        return self.centre + self.axis * self.length / 2

    @property
    def bottom(self) -> np.ndarray:
        return self.centre - self.axis * self.length / 2


def _fold(normals: np.ndarray) -> np.ndarray:
    """Integer bin keys with each direction folded onto its opposite: the first non-zero
    of the z, y, x components is made positive."""
    keys = np.round(normals / BIN).astype(np.int64)
    sign = np.ones(len(keys), dtype=np.int64)
    undecided = np.ones(len(keys), dtype=bool)
    for k in (2, 1, 0):
        nonzero = undecided & (keys[:, k] != 0)
        sign[nonzero] = np.sign(keys[nonzero, k])
        undecided &= ~nonzero
    return keys * sign[:, None], sign


def insert_frame(vertices, triangles, length: float, diameter: float,
                 tolerance: float) -> InsertFrame:
    """Find the insert's axis and check its size against the profile. Raises BodySizeError."""
    vertices = np.asarray(vertices, dtype=np.float64)
    corners = vertices[np.asarray(triangles)]
    normals, areas = normals_and_areas(corners)
    keep = areas > MIN_AREA
    if not keep.any():
        raise BodySizeError("the body has no geometry")
    normals, areas, centroids = normals[keep], areas[keep], corners[keep].mean(axis=1)
    keys, sign = _fold(normals)
    unique, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    totals = np.bincount(inverse, weights=areas)

    best = None
    for b in np.argsort(-totals)[:CANDIDATES]:
        members = inverse == b
        axis = (normals[members] * (sign[members] * areas[members])[:, None]).sum(axis=0)
        axis /= np.linalg.norm(axis)
        if axis[2] < 0:
            axis = -axis
        # The cap triangles' area-weighted centroid lies on the axis of a symmetric body.
        point = np.average(centroids[members], axis=0, weights=areas[members])
        along = (vertices - point) @ axis
        across = (vertices - point) - along[:, None] * axis
        measured_length = float(along.max() - along.min())
        measured_diameter = float(2 * np.sqrt(np.einsum("ij,ij->i", across, across).max()))
        if best is None:
            best = (measured_length, measured_diameter)
        if (abs(measured_length - length) <= tolerance
                and abs(measured_diameter - diameter) <= tolerance):
            centre = point + axis * (along.max() + along.min()) / 2
            return InsertFrame(axis, centre, measured_length, measured_diameter)
    raise BodySizeError("the body does not measure like the profile's insert", measured=best)
