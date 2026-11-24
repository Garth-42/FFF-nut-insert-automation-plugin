"""Find heat-set insert bodies and check them: one record per insert, per copy.

docs/heatset-plan.md, "Detection". A part is an insert when its name carries the HEATSET_
marker (nutcore.naming); its key picks the heat-set profile. The host is every part of
the same object that prints and is not a nut or insert body. Records are nutcore report
records with kind "heatset", so the panel, the tab and the slice gate can show them
beside the nuts.
"""

from __future__ import annotations

import numpy as np

from nutcore import naming
from nutcore.library import Library
from nutcore.mesh import ModelSnapshot, bed_mesh, normals_and_areas
from nutcore.report import NutRecord, status_of

from . import checks
from .hole import INVERTED, UPRIGHT, _plane, measure_hole
from .insert import BodySizeError, insert_frame


def detect_inserts(snapshot: ModelSnapshot, lib: Library, first_index: int = 1) -> list:
    """A record for every HEATSET_ body in every copy, numbered from first_index."""
    records: list[NutRecord] = []
    keys = lib.insert_keys()
    for oi, obj in enumerate(snapshot.objects, start=1):
        is_insert = [naming.looks_like_insert(part.name) for part in obj.parts]
        if not any(is_insert):
            continue
        printing = [not mark and not naming.looks_like_nut(part.name)
                    and part.kind in ("part", "unknown")
                    for part, mark in zip(obj.parts, is_insert, strict=True)]
        for ii, inst in enumerate(obj.instances, start=1):
            meshes = [bed_mesh(part, inst) for part in obj.parts]
            walls = [m for m, ok in zip(meshes, printing, strict=True) if ok and len(m.triangles)]
            host = np.concatenate([m.corners() for m in walls]) if walls else np.zeros((0, 3, 3))
            hold = footprint(host)
            for pi, (part, mesh, mark) in enumerate(
                    zip(obj.parts, meshes, is_insert, strict=True), start=1):
                if not mark:
                    continue
                record = NutRecord(index=first_index + len(records), object=oi, instance=ii,
                                   part=pi, name=part.name, kind="heatset")
                _detect(record, mesh, host, lib, keys, hold)
                if part.kind == "part":
                    record.add("E_NOT_MODIFIER", f"{record.label}: this insert body is still a "
                               "printing part, so it would print as plastic and fill its own "
                               "hole. Select it in the object list, right-click, Change type, "
                               "Modifier.")
                record.status = status_of(record.findings)
                records.append(record)
    return records


def footprint(host: np.ndarray) -> tuple[float, float]:
    """(area on the bed in mm², height in mm) of the printing parts of one copy."""
    if len(host) == 0:
        return 0.0, 0.0
    z = host[:, :, 2]
    bottom = z.min()
    normals, areas = normals_and_areas(host)
    on_bed = np.all(np.abs(z - bottom) < 0.01, axis=1) & (np.abs(normals[:, 2]) > 0.99)
    return float(areas[on_bed].sum()), float(z.max() - bottom)


def _detect(record: NutRecord, mesh, host, lib: Library, keys, hold) -> None:
    """Fill one record. Stops at the first step that makes later steps meaningless."""
    settings, label = lib.settings, record.label
    if len(mesh.vertices) == 0 or len(mesh.triangles) == 0:
        record.add("E_BODY_SIZE", f"{label}: the body has no geometry.")
        return
    lo, hi = mesh.vertices.min(axis=0), mesh.vertices.max(axis=0)
    record.box = {"centre": ((lo + hi) / 2).tolist(), "axes": np.eye(3).tolist(),
                  "half": ((hi - lo) / 2).tolist()}
    record.modelled_centre = record.box["centre"]

    prof = lib.heatset_profile(naming.match_insert_key(record.name, keys))
    if prof is None:
        known = ", ".join(f"HEATSET_{k}" for k in keys) or "none"
        record.add("E_NAME_UNKNOWN", f"{label}: no heat-set profile matches this name. Known "
                   f"names: {known}. Rename the body or add the tool's profile in the Nut panel.")
        return
    record.key = prof["insert_key"]
    try:
        frame = insert_frame(mesh.vertices, mesh.triangles, prof["insert_length"],
                             prof["insert_od"], settings.body_tolerance_mm)
    except BodySizeError as exc:
        text = f"{label}: {exc}"
        if exc.measured:
            text = (f"{label}: body measures {exc.measured[0]:.2f} mm long and "
                    f"{exc.measured[1]:.2f} mm across, but {prof['insert_key']} is "
                    f"{prof['insert_length']:.2f} mm long and {prof['insert_od']:.2f} mm across")
        record.add("E_BODY_SIZE", text + ". Fix the body in CAD, check the object's scale, "
                   "or rename the body to the right insert.")
        return
    record.axis, record.tilt_deg = frame.axis.tolist(), frame.tilt_deg
    record.body_size = [frame.diameter, frame.diameter, frame.length]
    record.modelled_centre = frame.centre.tolist()
    if frame.tilt_deg > settings.axis_tolerance_deg:
        record.cls = checks.TILTED
        record.findings.append(checks.orientation_finding(label, record.cls, frame.tilt_deg))
        return

    m = measure_hole(frame, host, prof)
    record.cls = m.cls
    if m.cls == INVERTED:
        record.findings.append(checks.orientation_finding(label, INVERTED, frame.tilt_deg))
        return
    record.findings += checks.check_insert(label, prof, frame, m, settings.axis_tolerance_deg)
    if m.cls != UPRIGHT:
        return                                  # no wall, or the hole is blocked
    a = frame.axis
    rim, bottom = m.at(a, m.s_rim), m.at(a, m.s_bottom)
    record.placement = [float(m.centre[0]), float(m.centre[1]), float(frame.centre[2])]
    record.z_low, record.z_high = float(frame.bottom[2]), float(frame.top[2])
    record.rim_z = float(rim[2])
    record.window = [record.rim_z, None]
    record.pocket = {"diameter": m.diameter, "depth": m.depth, "wall": m.wall,
                     "bottom_z": float(bottom[2]), "through": m.through,
                     "sink": float(rim[2] - frame.top[2]), "surface_tilt": m.surface_tilt}
    u, v = _plane(a)
    record.box = {"centre": ((rim + bottom) / 2).tolist(), "axes": [u.tolist(), v.tolist(),
                                                                    a.tolist()],
                  "half": [m.diameter / 2, m.diameter / 2, m.depth / 2]}
    held = checks.hold_down_finding(label, prof, *hold)
    if held:
        record.findings.append(held)
