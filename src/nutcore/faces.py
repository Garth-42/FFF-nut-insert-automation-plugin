"""Group a mesh's triangles into flat faces by normal and plane offset."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .mesh import normals_and_areas

PLANE_ANGLE_TOL = 0.5    # degrees
PLANE_OFFSET_TOL = 0.01  # mm
MIN_AREA = 1e-9          # mm^2, smaller triangles are dropped
MAX_DIRECTIONS = 40      # the largest faces are found first; a nut frame needs only six


@dataclass(frozen=True)
class FlatFace:
    normal: np.ndarray     # unit normal
    offset: float          # plane offset n . p
    area: float            # mm^2
    triangles: np.ndarray  # indices into the mesh's triangle array


def flat_faces(vertices, triangles, angle_tol_deg: float = PLANE_ANGLE_TOL,
               offset_tol: float = PLANE_OFFSET_TOL) -> list[FlatFace]:
    """Return the largest flat faces of a mesh, largest first.

    Only the MAX_DIRECTIONS largest directions are grouped. A real nut model has
    thousands of small facets in its threaded hole, and none of them matter here.

    Triangles are grouped by direction first (one loop per direction, not per
    triangle), then each direction is split where the plane offsets jump.
    """
    corners = np.asarray(vertices, dtype=np.float64)[np.asarray(triangles)]
    normals, areas = normals_and_areas(corners)
    index = np.flatnonzero(areas > MIN_AREA)
    normals, areas, centroids = normals[index], areas[index], corners[index].mean(axis=1)

    cos_tol = np.cos(np.radians(angle_tol_deg))
    remaining = np.ones(len(index), dtype=bool)
    faces: list[FlatFace] = []
    for _ in range(MAX_DIRECTIONS):
        if not remaining.any():
            break
        seed = np.argmax(np.where(remaining, areas, -1.0))
        members = np.flatnonzero(remaining & (normals @ normals[seed] >= cos_tol))
        remaining[members] = False
        normal = (normals[members] * areas[members, None]).sum(axis=0)
        normal /= np.linalg.norm(normal)
        offsets = centroids[members] @ normal
        order = np.argsort(offsets)
        breaks = np.flatnonzero(np.diff(offsets[order]) > offset_tol) + 1
        for group in np.split(order, breaks):
            ids = members[group]
            weight = areas[ids]
            faces.append(FlatFace(normal=normal,
                                  offset=float(np.average(offsets[group], weights=weight)),
                                  area=float(weight.sum()),
                                  triangles=index[ids]))
    faces.sort(key=lambda f: -f.area)
    return faces
