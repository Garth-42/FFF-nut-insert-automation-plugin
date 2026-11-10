"""Vectorised ray casting (Moller-Trumbore) and the robust "agreed wall" distance."""

from __future__ import annotations

import numpy as np

RAY_GRID = 5       # rays per face side
RAY_INSET = 0.8    # share of the face the grid covers
RAY_AGREE = 0.25   # share of rays that must agree on a wall
GAP_BIN = 0.01     # mm, histogram bin for gaps
GAP_EPS = 0.005    # mm, tolerance around a zero gap

_EDGE_EPS = 1e-9   # rays that graze a shared edge still count as hits
_MAX_PAIRS = 400_000


def cast(origins: np.ndarray, direction: np.ndarray, corners: np.ndarray) -> np.ndarray:
    """Distance along each ray to the nearest triangle, or inf.

    origins: (R, 3). direction: (3,) shared by all rays. corners: (T, 3, 3).
    Both sides of a triangle count.
    """
    origins = np.atleast_2d(np.asarray(origins, dtype=np.float64))
    result = np.full(len(origins), np.inf)
    if len(corners) == 0 or len(origins) == 0:
        return result
    d = np.asarray(direction, dtype=np.float64)
    v0 = corners[:, 0]
    e1 = corners[:, 1] - v0
    e2 = corners[:, 2] - v0
    pvec = np.cross(d, e2)                       # (T, 3)
    det = np.einsum("ij,ij->i", e1, pvec)        # (T,)
    usable = np.abs(det) > 1e-12                 # drop triangles parallel to the rays
    if not usable.any():
        return result
    v0, e1, e2, pvec = v0[usable], e1[usable], e2[usable], pvec[usable]
    inv = 1.0 / det[usable]

    step = max(1, _MAX_PAIRS // len(v0))
    for start in range(0, len(origins), step):
        o = origins[start:start + step]
        tvec = o[:, None, :] - v0[None, :, :]                 # (R, T, 3)
        bu = np.einsum("rtj,tj->rt", tvec, pvec) * inv
        qvec = np.cross(tvec, e1[None, :, :])
        bv = (qvec @ d) * inv
        t = np.einsum("rtj,tj->rt", qvec, e2) * inv
        hit = ((bu >= -_EDGE_EPS) & (bv >= -_EDGE_EPS) & (bu + bv <= 1 + _EDGE_EPS)
               & (t > _EDGE_EPS))
        result[start:start + step] = np.where(hit, t, np.inf).min(axis=1)
    return result


def face_grid(centre: np.ndarray, p: np.ndarray, hp: float, q: np.ndarray, hq: float,
              n: int = RAY_GRID, inset: float = RAY_INSET) -> np.ndarray:
    """An n x n grid of points over the central part of a rectangle, shape (n*n, 3)."""
    steps = np.linspace(-inset, inset, n)
    gp, gq = np.meshgrid(steps * hp, steps * hq, indexing="ij")
    return centre + gp.reshape(-1, 1) * p + gq.reshape(-1, 1) * q


def robust_nearest(values: np.ndarray, n_rays: int, agree: float = RAY_AGREE,
                   bin_size: float = GAP_BIN) -> float | None:
    """The smallest value that enough rays agree on, or None.

    Values are put in bins. The answer is the smallest value whose bin, together
    with its two neighbours, holds at least `agree` of all rays. Stray rays that
    fall into a bolt hole or a corner relief are outvoted this way.
    """
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return None
    bins = np.floor(values / bin_size).astype(np.int64)
    unique, counts = np.unique(bins, return_counts=True)
    count = dict(zip(unique.tolist(), counts.tolist(), strict=True))
    need = agree * n_rays - 1e-9
    for b in unique.tolist():
        if count.get(b - 1, 0) + count[b] + count.get(b + 1, 0) >= need:
            return float(values[bins == b].min())
    return None
