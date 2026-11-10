"""Mesh type, the model snapshot, transforms, an STL reader and feature edges."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Mesh:
    vertices: np.ndarray   # (N, 3) float64, mm
    triangles: np.ndarray  # (M, 3) int32

    def corners(self) -> np.ndarray:
        """Triangle corner points, shape (M, 3, 3)."""
        return self.vertices[self.triangles]


# --- The snapshot: all the core ever sees of the model -------------------------------------

@dataclass(frozen=True)
class PartSnapshot:
    name: str
    vertices: np.ndarray    # (N, 3) float64 copy, part-local, mm
    triangles: np.ndarray   # (M, 3) int32
    matrix: np.ndarray      # (4, 4) float64, part -> object


@dataclass(frozen=True)
class InstanceSnapshot:
    matrix: np.ndarray      # (4, 4) float64, object -> bed
    mirrored: bool


@dataclass(frozen=True)
class ObjectSnapshot:
    parts: tuple[PartSnapshot, ...]
    instances: tuple[InstanceSnapshot, ...]


@dataclass(frozen=True)
class ModelSnapshot:
    objects: tuple[ObjectSnapshot, ...]
    fingerprint: str        # hash of names, matrices, counts and bounds


def fingerprint(objects) -> str:
    """Hash of names, matrices, counts and bounds. Changes when the model changes."""
    h = hashlib.sha1()
    for obj in objects:
        h.update(b"O")
        for part in obj.parts:
            h.update(part.name.encode("utf-8", "replace"))
            h.update(np.asarray(part.matrix, dtype=np.float64).tobytes())
            h.update(struct.pack("<ii", len(part.vertices), len(part.triangles)))
            if len(part.vertices):
                h.update(np.asarray(part.vertices.min(axis=0), dtype=np.float64).tobytes())
                h.update(np.asarray(part.vertices.max(axis=0), dtype=np.float64).tobytes())
        for inst in obj.instances:
            h.update(np.asarray(inst.matrix, dtype=np.float64).tobytes())
            h.update(b"L" if inst.mirrored else b"R")
    return h.hexdigest()[:16]


def make_snapshot(objects) -> ModelSnapshot:
    objects = tuple(objects)
    return ModelSnapshot(objects=objects, fingerprint=fingerprint(objects))


# --- Transforms -----------------------------------------------------------------------------

def apply_matrix(vertices: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Apply a 4 x 4 matrix to (N, 3) points."""
    v = np.asarray(vertices, dtype=np.float64)
    return (np.c_[v, np.ones(len(v))] @ np.asarray(matrix, dtype=np.float64).T)[:, :3]


def bed_mesh(part: PartSnapshot, instance: InstanceSnapshot) -> Mesh:
    """One part of one copy, in bed coordinates."""
    matrix = instance.matrix @ part.matrix
    triangles = part.triangles[:, ::-1] if instance.mirrored else part.triangles
    return Mesh(apply_matrix(part.vertices, matrix), np.asarray(triangles, dtype=np.int32))


def translation(offset) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = offset
    return m


def rotation(axis, degrees: float) -> np.ndarray:
    """4 x 4 rotation about an axis ('x', 'y', 'z' or a vector) through the origin."""
    if isinstance(axis, str):
        axis = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[axis.lower()]
    k = np.asarray(axis, dtype=np.float64)
    k = k / np.linalg.norm(k)
    a = np.radians(degrees)
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    m = np.eye(4)
    m[:3, :3] = np.eye(3) + np.sin(a) * kx + (1 - np.cos(a)) * (kx @ kx)
    return m


def scaling(factor) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3] *= np.asarray(factor, dtype=np.float64) * np.ones(3)
    return m


# --- Triangle helpers -----------------------------------------------------------------------

def normals_and_areas(corners: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Unit normals (M, 3) and areas (M,) for triangle corners (M, 3, 3)."""
    cross = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    length = np.linalg.norm(cross, axis=1)
    safe = np.where(length > 0, length, 1.0)
    return cross / safe[:, None], length / 2


# --- STL reader -----------------------------------------------------------------------------

def read_stl(path) -> Mesh:
    """Read a binary or ASCII STL file. Identical corner points are merged."""
    data = Path(path).read_bytes()
    points = None
    if len(data) >= 84:
        count = struct.unpack_from("<I", data, 80)[0]
        if len(data) == 84 + 50 * count:
            records = np.frombuffer(data, dtype=np.dtype([
                ("normal", "<f4", 3), ("points", "<f4", (3, 3)), ("attr", "<u2")]),
                count=count, offset=84)
            points = records["points"].reshape(-1, 3).astype(np.float64)
    if points is None:
        values = [line.split()[1:4] for line in data.decode("ascii", "replace").splitlines()
                  if line.strip().startswith("vertex")]
        points = np.array(values, dtype=np.float64).reshape(-1, 3)
    if len(points) == 0 or len(points) % 3:
        raise ValueError(f"{path}: not a readable STL file")
    vertices, inverse = np.unique(points, axis=0, return_inverse=True)
    return Mesh(vertices, inverse.reshape(-1, 3).astype(np.int32))


# --- Feature edges for the preview ----------------------------------------------------------

def feature_edges(vertices, triangles, min_angle_deg: float = 20.0,
                  weld: float = 1e-4) -> tuple[np.ndarray, np.ndarray]:
    """Edges worth drawing: sharp edges and open boundaries.

    Returns (segments (K, 2, 3), angles (K,)). The angle is the turn between the
    two triangles at the edge, or 180 for a boundary edge.
    """
    v = np.asarray(vertices, dtype=np.float64)
    tri = np.asarray(triangles)
    if len(v) == 0 or len(tri) == 0:
        return np.zeros((0, 2, 3)), np.zeros(0)
    keys = np.round(v / weld).astype(np.int64)
    unique, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    pos = np.zeros((len(unique), 3))
    pos[inverse] = v
    tri = inverse[tri]
    tri = tri[(tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 0] != tri[:, 2])]
    if len(tri) == 0:
        return np.zeros((0, 2, 3)), np.zeros(0)
    normals, _ = normals_and_areas(pos[tri])

    edges = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
    edges.sort(axis=1)
    owner = np.tile(np.arange(len(tri)), 3)
    key = edges[:, 0] * len(unique) + edges[:, 1]
    order = np.argsort(key, kind="stable")
    _, start, counts = np.unique(key[order], return_index=True, return_counts=True)
    first = order[start]
    angle = np.full(len(start), 180.0)
    two = counts == 2
    second = order[start[two] + 1]
    cos = np.clip(np.sum(normals[owner[first[two]]] * normals[owner[second]], axis=1), -1, 1)
    angle[two] = np.degrees(np.arccos(cos))
    keep = angle > min_angle_deg
    return pos[edges[first[keep]]], angle[keep]


def limit_segments(segments: np.ndarray, angles: np.ndarray, limit: int) -> np.ndarray:
    """Keep at most `limit` segments, dropping the gentlest edges first."""
    if len(segments) <= limit:
        return segments
    keep = np.argpartition(-angles, limit - 1)[:limit]
    return segments[np.sort(keep)]
