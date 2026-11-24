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
from nutcore.report import NutRecord

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


# --- Heat-set inserts -----------------------------------------------------------------------

def _ring(radius, z, sides, centre=(0.0, 0.0)):
    a = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    return np.column_stack([centre[0] + radius * np.cos(a), centre[1] + radius * np.sin(a),
                            np.broadcast_to(np.asarray(z, dtype=float), (sides,))])


def _band(inner, outer):
    """Triangles joining two rings of the same size, stacked as vertices [inner, outer]."""
    n = len(inner)
    i = np.arange(n)
    j = (i + 1) % n
    tris = np.vstack([np.column_stack([i, j, n + i]), np.column_stack([j, n + j, n + i])])
    return Mesh(np.vstack([inner, outer]), tris.astype(np.int32))


def _disc(radius, z, sides, centre=(0.0, 0.0)):
    rim = _ring(radius, z, sides, centre)
    i = np.arange(sides)
    tris = np.column_stack([np.full(sides, sides), i, (i + 1) % sides])
    return Mesh(np.vstack([rim, [[centre[0], centre[1], z]]]), tris.astype(np.int32))


def _quad(a, b, c, d):
    return Mesh(np.array([a, b, c, d], dtype=float), np.array([[0, 1, 2], [0, 2, 3]],
                                                               dtype=np.int32))


def insert_body(od=4.6, length=5.7, sides=64, bore=None, knurl=0.0, centre=(0, 0, 0),
                rot=None, name="HEATSET_M3x5.7", kind="unknown") -> PartSnapshot:
    """A closed faceted cylinder along local Z, middle at `centre` after `rot`.

    bore: diameter of a hole along the axis. knurl: depth of a zig-zag on the outside.
    """
    radius = np.full(sides, od / 2) - knurl * (np.arange(sides) % 2)
    a = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    outer = np.column_stack([radius * np.cos(a), radius * np.sin(a)])
    lo, hi = -length / 2, length / 2
    o0 = np.column_stack([outer, np.full(sides, lo)])
    o1 = np.column_stack([outer, np.full(sides, hi)])
    parts = [_band(o0, o1)]
    if bore:
        b0, b1 = _ring(bore / 2, lo, sides), _ring(bore / 2, hi, sides)
        parts += [_band(b1, b0), _band(b0, o0), _band(o1, b1)]
    else:                                       # solid: a fan from the middle of each end
        i = np.arange(sides)
        fan0 = np.column_stack([np.full(sides, sides), (i + 1) % sides, i])
        fan1 = np.column_stack([np.full(sides, sides), i, (i + 1) % sides])
        parts += [Mesh(np.vstack([o0, [[0, 0, lo]]]), fan0.astype(np.int32)),
                  Mesh(np.vstack([o1, [[0, 0, hi]]]), fan1.astype(np.int32))]
    mesh = merge(parts)
    vertices = apply_matrix(mesh.vertices, rot) if rot is not None else mesh.vertices
    return part(name, Mesh(vertices + np.asarray(centre, dtype=float), mesh.triangles),
                kind=kind)


def hole_block(hole=4.0, depth=6.7, size=12.0, height=10.0, sides=64, step=None,
               chamfer=None, through=False, slope_deg=0.0, lid_gap=None, name="Boss",
               kind="unknown") -> PartSnapshot:
    """A square block standing on Z 0 with a round hole down from its top face at Z height.

    Built from separate pieces, like pocket_block: the hole wall (a faceted tube with its
    vertices on the true circle), its floor unless through, the top face, four sides and
    the bottom. step=(diameter, depth): the hole narrows to a screw hole at that depth.
    chamfer=c: a 45° entry chamfer. slope_deg: the top face tilts about Y. lid_gap: a slab
    over the whole block, that far above its top face.
    """
    r, top, half = hole / 2, height, size / 2
    pieces = []
    wall_top = top - chamfer if chamfer else top
    if step:
        screw, step_depth = step[0] / 2, step[1]
        pieces += [_band(_ring(r, top - step_depth, sides), _ring(r, wall_top, sides)),
                   _band(_ring(screw, top - step_depth, sides), _ring(r, top - step_depth, sides)),
                   _band(_ring(screw, 0.0, sides), _ring(screw, top - step_depth, sides))]
        opening = screw
    else:
        bottom = 0.0 if through else top - depth
        pieces.append(_band(_ring(r, bottom, sides), _ring(r, wall_top, sides)))
        if not through:
            pieces.append(_disc(r, bottom, sides))
        opening = r
    if chamfer:
        pieces.append(_band(_ring(r, wall_top, sides), _ring(r + chamfer, top, sides)))
    edge = r + chamfer if chamfer else r
    inner, outer = _ring(edge, 0.0, sides), _ring(half, 0.0, sides)
    slope = np.tan(np.radians(slope_deg))
    inner[:, 2], outer[:, 2] = top + slope * inner[:, 0], top + slope * outer[:, 0]
    pieces.append(_band(inner, outer))
    for (x0, y0), (x1, y1) in (((-half, -half), (half, -half)), ((half, -half), (half, half)),
                               ((half, half), (-half, half)), ((-half, half), (-half, -half))):
        pieces.append(_quad((x0, y0, 0), (x1, y1, 0), (x1, y1, top), (x0, y0, top)))
    if through or step:                       # the bottom, around a square opening
        g = opening + 0.1
        pieces += [_quad((-half, g, 0), (-half, half, 0), (half, half, 0), (half, g, 0)),
                   _quad((-half, -half, 0), (-half, -g, 0), (half, -g, 0), (half, -half, 0)),
                   _quad((g, -g, 0), (g, g, 0), (half, g, 0), (half, -g, 0)),
                   _quad((-half, -g, 0), (-half, g, 0), (-g, g, 0), (-g, -g, 0))]
    else:
        pieces.append(_quad((-half, -half, 0), (-half, half, 0), (half, half, 0),
                            (half, -half, 0)))
    if lid_gap is not None:
        pieces.append(box((size, size, 1.0), (0, 0, top + lid_gap + 0.5)))
    return part(name, merge(pieces), kind=kind)


def sample_record():
    """The nut record the plugin reported in Orca for tests/data/sample.gcode.

    Garth's export from OrcaSlicer 2.5.0 (Voron 2.4, Klipper, 0.2 mm layers) of a block
    with one roofed pocket, 5.8 x 5.8 x 2.0, floor at Z 1.0 and roof at Z 3.0.
    """
    return NutRecord(
        index=1, object=1, instance=1, part=1, name="NUT_M3SQ", key="M3SQ", cls="FLAT",
        axis=[0, 0, 1], yaw_deg=0.0, tilt_deg=0.0, body_size=[5.5, 5.5, 1.8],
        placement=[164.706, 158.320, 1.9], z_low=1.0, z_high=2.8, roof_z=3.0,
        pocket={"width": [5.8, 5.8], "thickness": None, "depth": 2.0, "seat_gaps": [0.0]},
        box={"centre": [164.706, 158.320, 2.0], "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
             "half": [2.9, 2.9, 1.0]},
        window=[2.9, 3.0])


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
