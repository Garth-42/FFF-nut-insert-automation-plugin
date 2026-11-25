"""Test models for the heat-set checks: closed meshes of coupons with holes, written as 3MF.

    uv run python tests/models3mf.py          writes models/heatset_*.3mf

Each coupon is one object: a block with a round hole (part "Coupon") and the insert body in
it (part "HEATSET_M3x5.7"). tests/test_models.py reads the files back, checks every mesh is
closed with its faces outward, and runs the plugin's detection on them, expecting each
coupon's findings. models/README.md says what Orca should show.
"""

from __future__ import annotations

import math
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

from nutcore.mesh import (
    InstanceSnapshot,
    ObjectSnapshot,
    PartSnapshot,
    make_snapshot,
    rotation,
    translation,
)

ROOT = Path(__file__).parents[1]
SIDES = 64                    # facets around a hole or an insert body
NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
INSERT = "HEATSET_M3x5.7"


# --- Closed meshes --------------------------------------------------------------------------

def _ring(radius: float, n: int) -> list[tuple[float, float]]:
    return [(radius * math.cos(2 * math.pi * i / n), radius * math.sin(2 * math.pi * i / n))
            for i in range(n)]


def _outline(sx: float, sy: float, n: int):
    """The rectangle's outline as seen from its middle along the ring's n angles, with its
    corners added: the points in order, and where each angle's point is in that order."""
    hx, hy = sx / 2, sy / 2
    points, starts = [], []
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        c, s = math.cos(a0), math.sin(a0)
        t = min(hx / abs(c) if abs(c) > 1e-12 else math.inf,
                hy / abs(s) if abs(s) > 1e-12 else math.inf)
        starts.append(len(points))
        points.append((t * c, t * s))
        for cx, cy in ((hx, hy), (-hx, hy), (-hx, -hy), (hx, -hy)):
            corner = math.atan2(cy, cx) % (2 * math.pi)
            if a0 + 1e-9 < corner < a1 - 1e-9:
                points.append((cx, cy))
    return points, starts


def block_with_hole(sx: float, sy: float, height: float, hole_d: float, depth: float,
                    through: bool = False, n: int = SIDES):
    """A block standing on Z 0, its top at height, with a round hole down from the top."""
    v: list[tuple[float, float, float]] = []

    def add(points, z):
        first = len(v)
        v.extend((x, y, z) for x, y in points)
        return list(range(first, len(v)))

    floor = 0.0 if through else height - depth
    inner = _ring(hole_d / 2, n)
    outline, starts = _outline(sx, sy, n)
    in_top, in_low = add(inner, height), add(inner, floor)
    out_top, out_low = add(outline, height), add(outline, 0.0)
    m, t = len(outline), []

    def chain(ring, i):
        end = starts[i + 1] if i + 1 < n else m
        return [ring[j % m] for j in range(starts[i], end + 1)]

    for i in range(n):
        j = (i + 1) % n
        top = chain(out_top, i)                     # top face: the hole's rim to the outline
        t += [(in_top[i], top[k], top[k + 1]) for k in range(len(top) - 1)]
        t.append((in_top[i], top[-1], in_top[j]))
        t += [(in_low[j], in_low[i], in_top[i]), (in_low[j], in_top[i], in_top[j])]  # hole wall
        if through:
            low = chain(out_low, i)                 # underside: an annulus, facing down
            t += [(in_low[i], low[k + 1], low[k]) for k in range(len(low) - 1)]
            t.append((in_low[i], in_low[j], low[-1]))
    for k in range(m):                              # the four sides
        a, b = k, (k + 1) % m
        t += [(out_low[a], out_low[b], out_top[b]), (out_low[a], out_top[b], out_top[a])]
    if not through:
        (centre,) = add([(0.0, 0.0)], floor)        # the hole's floor, facing up
        t += [(centre, in_low[i], in_low[(i + 1) % n]) for i in range(n)]
        (middle,) = add([(0.0, 0.0)], 0.0)          # the underside, facing down
        t += [(middle, out_low[(k + 1) % m], out_low[k]) for k in range(m)]
    return np.array(v), np.array(t, dtype=np.int32)


def cylinder(diameter: float, length: float, n: int = SIDES):
    """A closed cylinder along Z, its middle at the origin: an insert body."""
    ring = _ring(diameter / 2, n)
    v = [(x, y, -length / 2) for x, y in ring] + [(x, y, length / 2) for x, y in ring]
    v += [(0.0, 0.0, -length / 2), (0.0, 0.0, length / 2)]
    low, top, cb, ct = 0, n, 2 * n, 2 * n + 1
    t = []
    for i in range(n):
        j = (i + 1) % n
        t += [(low + i, low + j, top + j), (low + i, top + j, top + i),
              (ct, top + i, top + j), (cb, low + j, low + i)]
    return np.array(v), np.array(t, dtype=np.int32)


# --- The coupons ----------------------------------------------------------------------------

@dataclass
class Coupon:
    name: str
    expected: list                    # the finding codes detection should give
    size: tuple = (16.0, 16.0, 10.0)
    hole: float = 4.0
    depth: float = 6.7
    through: bool = False
    body: str = INSERT
    body_od: float = 4.6
    body_length: float = 5.7
    offset: tuple = (0.0, 0.0, 0.0)   # the body moved from flush on the hole's axis
    tilt: float = 0.0                 # degrees about X, the whole object
    notes: str = ""
    at: tuple = field(default=(0.0, 0.0))

    def parts(self):
        block = block_with_hole(*self.size, self.hole, self.depth, self.through)
        body = cylinder(self.body_od, self.body_length)
        x, y, dz = self.offset
        place = translation((x, y, self.size[2] - self.body_length / 2 + dz))
        return [("Coupon", *block, np.eye(4)), (self.body, *body, place)]

    def matrix(self):
        lift = (self.size[1] / 2) * math.sin(math.radians(self.tilt))
        return translation((*self.at, lift)) @ rotation("x", self.tilt)


CHECKS = [
    Coupon("1 good", [], notes="An insert that passes every check."),
    Coupon("2 wide hole", ["E_HOLE_DIAMETER"], hole=4.3, notes="The hole is 4.3 mm across."),
    Coupon("3 shallow hole", ["E_DEPTH"], depth=6.0, notes="The hole is 6.0 mm deep."),
    Coupon("4 thin wall", ["E_WALL"], size=(7.0, 20.0, 10.0), notes="1.5 mm of wall."),
    Coupon("5 through hole", [], size=(16.0, 16.0, 6.0), through=True,
           notes="No depth rule for a through hole."),
    Coupon("6 off centre", ["N_OFF_CENTRE"], offset=(0.2, 0.0, 0.0),
           notes="The body sits 0.2 mm off the hole's axis; the hole's axis is used."),
    Coupon("7 unknown insert", ["E_NAME_UNKNOWN"], body="HEATSET_M4x8",
           notes="No heat-set profile has the key M4x8."),
    Coupon("8 tilted", ["W_TILTED"], tilt=20.0, notes="Tilted 20 degrees: fit it by hand."),
    Coupon("9 body below the floor", ["E_INTERFERENCE"], offset=(0.0, 0.0, -1.5),
           notes="The body reaches 0.5 mm below the hole's floor."),
    Coupon("10 small and tall", ["W_HOLD_DOWN"], size=(8.0, 8.0, 30.0),
           notes="8 x 8 mm on the bed and 30 mm tall: it may tip under the press."),
]
for _i, _c in enumerate(CHECKS):
    _c.at = (40.0 + 45.0 * (_i % 5), 60.0 + 60.0 * (_i // 5))

BRINGUP = [Coupon("Heat-set bring-up coupon", [], size=(30.0, 30.0, 8.0), at=(150.0, 150.0),
                  notes="One good hole for the first rehearse runs and the first insert.")]

FILES = {"heatset_check_coupons.3mf": CHECKS, "heatset_bringup_coupon.3mf": BRINGUP}


# --- 3MF ------------------------------------------------------------------------------------

def _number(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _transform(m: np.ndarray) -> str:
    """3MF's 3 x 4 row-vector form of a 4 x 4 column-vector matrix."""
    return " ".join(_number(m[r, c]) for c in range(4) for r in range(3))


def model_xml(coupons) -> bytes:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             f'<model unit="millimeter" xml:lang="en-US" xmlns="{NS}">',
             ' <metadata name="Title">Heat-set test coupons</metadata>', " <resources>"]
    items, next_id = [], 1
    for coupon in coupons:
        components = []
        for name, vertices, triangles, matrix in coupon.parts():
            lines.append(f'  <object id="{next_id}" name="{name}" type="model"><mesh><vertices>')
            lines += [f'   <vertex x="{_number(x)}" y="{_number(y)}" z="{_number(z)}"/>'
                      for x, y, z in vertices]
            lines.append("  </vertices><triangles>")
            lines += [f'   <triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in triangles]
            lines.append("  </triangles></mesh></object>")
            components.append(f'   <component objectid="{next_id}" '
                              f'transform="{_transform(matrix)}"/>')
            next_id += 1
        lines.append(f'  <object id="{next_id}" name="{coupon.name}" type="model"><components>')
        lines += components + ["  </components></object>"]
        items.append(f'  <item objectid="{next_id}" transform="{_transform(coupon.matrix())}"/>')
        next_id += 1
    lines += [" </resources>", " <build>", *items, " </build>", "</model>", ""]
    return "\n".join(lines).encode("utf-8")


_CONTENT_TYPES = b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
"""
_RELS = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""


def write_3mf(path: Path, coupons) -> None:
    """A deterministic file: fixed member order, times and compression."""
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in (("[Content_Types].xml", _CONTENT_TYPES), ("_rels/.rels", _RELS),
                           ("3D/3dmodel.model", model_xml(coupons))):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 24, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)


def _matrix(text: str | None) -> np.ndarray:
    m = np.eye(4)
    if text:
        values = [float(x) for x in text.split()]
        for c in range(4):
            for r in range(3):
                m[r, c] = values[3 * c + r]
    return m


def read_3mf(path: Path):
    """The file as Orca would load it, each object's parts in one object: a ModelSnapshot,
    with insert bodies already set to Modifier, and the object names in order."""
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("3D/3dmodel.model"))
    q = f"{{{NS}}}"
    objects = {o.get("id"): o for o in root.iter(q + "object")}
    snapshots, names = [], []
    for item in root.iter(q + "item"):
        obj = objects[item.get("objectid")]
        parts = []
        for component in obj.iter(q + "component"):
            mesh_object = objects[component.get("objectid")]
            vertices = np.array([[float(v.get(a)) for a in "xyz"]
                                 for v in mesh_object.iter(q + "vertex")])
            triangles = np.array([[int(t.get(a)) for a in ("v1", "v2", "v3")]
                                  for t in mesh_object.iter(q + "triangle")], dtype=np.int32)
            name = mesh_object.get("name")
            parts.append(PartSnapshot(name=name, vertices=vertices, triangles=triangles,
                                      matrix=_matrix(component.get("transform")),
                                      kind="modifier" if name.startswith("HEATSET_") else "part"))
        matrix = _matrix(item.get("transform"))
        snapshots.append(ObjectSnapshot(parts=tuple(parts), instances=(InstanceSnapshot(
            matrix=matrix, mirrored=bool(np.linalg.det(matrix[:3, :3]) < 0)),)))
        names.append(obj.get("name"))
    return make_snapshot(snapshots), names


def main() -> None:
    out = ROOT / "models"
    out.mkdir(exist_ok=True)
    for name, coupons in FILES.items():
        write_3mf(out / name, coupons)
        print(f"wrote models/{name}: {len(coupons)} coupon(s)")


if __name__ == "__main__":
    main()
