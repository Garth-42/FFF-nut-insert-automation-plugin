"""Synthetic meshes and G-code for the tests. Nothing here needs a file on disk."""

from __future__ import annotations

import numpy as np

from nutcore import library
from nutcore.mesh import (
    InstanceSnapshot,
    Mesh,
    ObjectSnapshot,
    PartSnapshot,
    apply_matrix,
    make_snapshot,
    rotation,
)

_CUBE = np.array([[x, y, z] for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)])
# Corner index = 4x + 2y + z. Two triangles per side, wound to face outward.
_CUBE_TRIS = np.array([
    [0, 1, 3], [0, 3, 2],   # -x
    [4, 6, 7], [4, 7, 5],   # +x
    [0, 4, 5], [0, 5, 1],   # -y
    [2, 3, 7], [2, 7, 6],   # +y
    [0, 2, 6], [0, 6, 4],   # -z
    [1, 5, 7], [1, 7, 3],   # +z
], dtype=np.int32)


def box(size, centre=(0, 0, 0), rot=None) -> Mesh:
    """A 12-triangle box. `rot` is a 4 x 4 rotation applied about the box's own centre."""
    vertices = _CUBE * np.asarray(size, dtype=float)
    if rot is not None:
        vertices = apply_matrix(vertices, rot)
    return Mesh(vertices + np.asarray(centre, dtype=float), _CUBE_TRIS.copy())


def merge(meshes) -> Mesh:
    vertices, triangles, offset = [], [], 0
    for mesh in meshes:
        vertices.append(mesh.vertices)
        triangles.append(mesh.triangles + offset)
        offset += len(mesh.vertices)
    return Mesh(np.concatenate(vertices), np.concatenate(triangles).astype(np.int32))


def part(name: str, mesh: Mesh, matrix=None, kind="unknown") -> PartSnapshot:
    return PartSnapshot(name=name, vertices=mesh.vertices, triangles=mesh.triangles,
                        matrix=np.eye(4) if matrix is None else matrix, kind=kind)


def nut(key="M3SQ", centre=(0, 0, 0), rot=None, name=None, size=None) -> PartSnapshot:
    """A box of the library size named NUT_<key>. Its thread axis is local Z before `rot`."""
    if size is None:
        entry = next(n for n in library.default_config()["nuts"] if n["key"] == "M3SQ")
        size = (entry["across_flats"], entry["across_flats"], entry["thickness"])
    return part(name or f"NUT_{key}", box(size, centre, rot))


def pocket_block(inner=(5.8, 5.8, 2.0), wall=3.0, floor=4.4, roof=1.0, bolt_hole=None,
                 origin=(0, 0, 0), extra=(), name="Bracket") -> PartSnapshot:
    """A host made of separate boxes around a pocket.

    The pocket floor's centre is at `origin`. inner = (size x, size y, depth).
    roof is the roof slab's thickness, or None for an open top. bolt_hole is the
    side of a square hole through the floor.
    """
    wx, wy, depth = inner
    ox, oy = wx + 2 * wall, wy + 2 * wall
    boxes = []
    if bolt_hole:
        s = bolt_hole
        strip = (oy - s) / 2
        boxes.append(box((ox, strip, floor), (0, s / 2 + strip / 2, -floor / 2)))
        boxes.append(box((ox, strip, floor), (0, -s / 2 - strip / 2, -floor / 2)))
        side = (ox - s) / 2
        boxes.append(box((side, s, floor), (s / 2 + side / 2, 0, -floor / 2)))
        boxes.append(box((side, s, floor), (-s / 2 - side / 2, 0, -floor / 2)))
    else:
        boxes.append(box((ox, oy, floor), (0, 0, -floor / 2)))
    boxes.append(box((wall, oy, depth), (wx / 2 + wall / 2, 0, depth / 2)))
    boxes.append(box((wall, oy, depth), (-wx / 2 - wall / 2, 0, depth / 2)))
    boxes.append(box((wx, wall, depth), (0, wy / 2 + wall / 2, depth / 2)))
    boxes.append(box((wx, wall, depth), (0, -wy / 2 - wall / 2, depth / 2)))
    if roof:
        boxes.append(box((ox, oy, roof), (0, 0, depth + roof / 2)))
    boxes.extend(extra)
    mesh = merge(boxes)
    return part(name, Mesh(mesh.vertices + np.asarray(origin, dtype=float), mesh.triangles))


def v_slot(gap_plus_y=0.1, gap_minus_y=0.1, thickness=2.1, opening=8.08, roof_z=4.5,
           across_flats=5.5, name="Bracket") -> PartSnapshot:
    """A V slot for a nut standing on a corner, thread axis along X.

    The modelled nut centre is the origin. Each lower flat faces a slab at the
    given gap. Vertical walls stand beside the side corners, and a roof closes the slot.
    """
    half = across_flats / 2
    slab_t = 2.0
    boxes = []
    for sign, gap in ((1.0, gap_plus_y), (-1.0, gap_minus_y)):
        normal = np.array([0.0, sign, -1.0]) / np.sqrt(2)
        boxes.append(box((thickness + 6, 4.6, slab_t), normal * (half + gap + slab_t / 2),
                         rotation("x", sign * 45)))
    for sign in (1.0, -1.0):
        boxes.append(box((3, 14, 14), (sign * (thickness / 2 + 1.5), 0, 1)))
        boxes.append(box((thickness + 6, 3, roof_z + 1.5),
                         (0, sign * (opening / 2 + 1.5), (roof_z - 1.5) / 2)))
    boxes.append(box((thickness + 6, 14, 1), (0, 0, roof_z + 0.5)))
    return part(name, merge(boxes))


def snapshot(parts, instance_matrices=None):
    """Wrap parts as one object in a ModelSnapshot."""
    matrices = [np.eye(4)] if instance_matrices is None else instance_matrices
    instances = tuple(InstanceSnapshot(matrix=np.asarray(m, dtype=float),
                                       mirrored=bool(np.linalg.det(np.asarray(m)[:3, :3]) < 0))
                      for m in matrices)
    return make_snapshot([ObjectSnapshot(parts=tuple(parts), instances=instances)])


# --- Synthetic G-code -----------------------------------------------------------------------

def gcode_ring(centre=(112.4, 87.25), inner=(5.8, 5.8), floor_z=4.4, roof_z=6.4, top_z=7.4,
               layer=0.2, fill_inside=False, relative_e=True, arc_inside=False, header=True,
               newline="\n", fall_back=False, tool=0, ring_offset=0.6) -> str:
    """G-code for a block with a rectangular pocket.

    Layers whose middle is below the floor or above the roof are solid: lines
    cross the whole footprint. Layers in between print only a ring around the
    pocket. roof_z=None gives an open-top pocket that ends at top_z.
    fill_inside adds a line through the pocket in the open layers, arc_inside
    adds an arc there, and fall_back re-prints a low layer near the end.
    """
    centres = [centre] if isinstance(centre[0], (int, float)) else list(centre)
    cx, cy = centres[0]
    hx, hy = inner[0] / 2 + ring_offset, inner[1] / 2 + ring_offset
    lines = []
    if header:
        lines += ["; HEADER_BLOCK_START", "; generated by tests/builders.py",
                  "; HEADER_BLOCK_END"]
    lines += ["G90", "M83" if relative_e else "M82", "G28", f"T{tool}", "G92 E0"]
    e_total = 0.0

    def extrude(x, y, command="G1", extra=""):
        nonlocal e_total
        e_total += 0.05
        e = 0.05 if relative_e else e_total
        lines.append(f"{command} X{x:.3f} Y{y:.3f}{extra} E{e:.5f}")

    def ring():
        lines.append(f"G0 X{cx - hx:.3f} Y{cy - hy:.3f}")
        for x, y in ((cx + hx, cy - hy), (cx + hx, cy + hy), (cx - hx, cy + hy),
                     (cx - hx, cy - hy)):
            extrude(x, y)

    def solid():
        ring()
        for k in range(-2, 3):
            y = cy + k * inner[1] / 5
            lines.append(f"G0 X{cx - hx:.3f} Y{y:.3f}")
            extrude(cx + hx, y)

    def one_layer(z):
        nonlocal cx, cy
        lines.append(f"G1 Z{z:.3f} F600")
        for point in centres:
            cx, cy = point
            one_pocket(z)

    def one_pocket(z):
        mid = z - layer / 2
        is_open = mid > floor_z + 1e-9 and (roof_z is None or mid < roof_z - 1e-9)
        if not is_open:
            solid()
            return
        ring()
        if fill_inside:
            lines.append(f"G0 X{cx - 1:.3f} Y{cy:.3f}")
            extrude(cx + 1, cy)
        if arc_inside:
            # Half circle of radius 1.5 from the pocket's left to its right, through the middle.
            lines.append(f"G0 X{cx - 1.5:.3f} Y{cy:.3f}")
            extrude(cx + 1.5, cy, command="G2", extra=" I1.5 J0")

    count = int(round(top_z / layer))
    for i in range(1, count + 1):
        one_layer(i * layer)
    if fall_back:
        one_layer(3 * layer)
    lines += ["G1 E-0.8 F1800", "M104 S0", "; end"]
    return newline.join(lines) + newline
