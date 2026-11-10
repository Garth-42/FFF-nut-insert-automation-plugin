"""detect(snapshot, config) -> Report: the whole detection pipeline as one pure function."""

from __future__ import annotations

import numpy as np

from . import checker, library, naming
from .faces import flat_faces
from .frame import PLACEABLE, BodySizeError, classify, nut_frame
from .mesh import ModelSnapshot, apply_matrix, bed_mesh, feature_edges, limit_segments
from .pocket import measure
from .report import NutRecord, Report, status_of

MAX_EDGE_SEGMENTS = 20_000


def _bounds_box(vertices: np.ndarray) -> dict:
    """An axis-aligned box around a body, for nuts that could not be measured."""
    lo, hi = vertices.min(axis=0), vertices.max(axis=0)
    return {"centre": ((lo + hi) / 2).tolist(), "axes": np.eye(3).tolist(),
            "half": ((hi - lo) / 2).tolist()}


def detect(snapshot: ModelSnapshot, config: dict | library.Library) -> Report:
    """Find every nut in the snapshot, measure its pocket and check it against the library."""
    lib = config if isinstance(config, library.Library) else library.parse(config)
    report = Report(fingerprint=snapshot.fingerprint)
    keys = lib.keys()

    for oi, obj in enumerate(snapshot.objects, start=1):
        nut_parts = [naming.looks_like_nut(part.name) for part in obj.parts]
        if not any(nut_parts):
            continue
        for ii, inst in enumerate(obj.instances, start=1):
            meshes = [bed_mesh(part, inst) for part in obj.parts]
            # Walls are the parts that print. Modifiers, support blockers and the like
            # are not plastic, so they are not walls.
            host_parts = [m.corners() for m, part, is_nut
                          in zip(meshes, obj.parts, nut_parts, strict=True)
                          if not is_nut and part.kind in ("part", "unknown")
                          and len(m.triangles)]
            host = np.concatenate(host_parts) if host_parts else np.zeros((0, 3, 3))
            for pi, (part, mesh, is_nut) in enumerate(
                    zip(obj.parts, meshes, nut_parts, strict=True), start=1):
                if not is_nut:
                    continue
                record = NutRecord(index=len(report.nuts) + 1, object=oi, instance=ii, part=pi,
                                   name=part.name)
                _detect_nut(record, mesh, host, lib, keys)
                if part.kind == "part":
                    record.add("E_NOT_MODIFIER", f"{record.label}: this nut body is still a "
                               "printing part, so it would print as plastic and fill its own "
                               "pocket. Select it in the object list, right-click, Change "
                               "type, Modifier.")
                record.status = status_of(record.findings)
                report.nuts.append(record)
    return report


def _detect_nut(record: NutRecord, mesh, host, lib: library.Library, keys) -> None:
    """Fill one record. Stops at the first step that makes later steps meaningless."""
    settings = lib.settings
    label = record.label
    if len(mesh.vertices) == 0 or len(mesh.triangles) == 0:
        record.add("E_BODY_SIZE", f"{label}: the body has no geometry.")
        return
    record.box = _bounds_box(mesh.vertices)
    record.modelled_centre = record.box["centre"]

    key = naming.match_key(record.name, keys)
    nut = lib.get(key)
    if nut is None:
        known = ", ".join(f"NUT_{k}" for k in keys) or "none"
        record.add("E_NAME_UNKNOWN", f"{label}: no nut library entry matches this name. "
                   f"Known names: {known}. Rename the body or add the nut type in the Nut panel.")
        return
    record.key = nut.key

    try:
        frame = nut_frame(mesh.vertices, flat_faces(mesh.vertices, mesh.triangles),
                          nut.across_flats, nut.thickness, settings.axis_tolerance_deg,
                          settings.body_tolerance_mm)
    except BodySizeError as exc:
        text = f"{label}: {exc}"
        if exc.measured:
            record.body_size = list(exc.measured)
            text = (f"{label}: body measures " + " × ".join(f"{e:.2f}" for e in exc.measured)
                    + f" mm, but {nut.key} is {nut.across_flats:.2f} × {nut.across_flats:.2f}"
                    f" × {nut.thickness:.2f} mm")
        record.add("E_BODY_SIZE", text + ". Fix the body in CAD, check the object's scale, "
                   "or rename the body to the right nut type.")
        return

    orientation = classify(frame, settings.axis_tolerance_deg)
    frame = orientation.frame
    record.cls = orientation.cls
    record.axis = frame.a.tolist()
    record.yaw_deg = orientation.yaw_deg
    record.tilt_deg = orientation.tilt_deg
    record.roll_deg = orientation.roll_deg
    record.body_size = list(frame.body_size)
    record.modelled_centre = frame.centre.tolist()
    record.box = {"centre": frame.centre.tolist(),
                  "axes": [frame.u.tolist(), frame.v.tolist(), frame.a.tolist()],
                  "half": [frame.hu, frame.hv, frame.ha]}

    if orientation.cls not in PLACEABLE:
        record.findings.append(checker.orientation_finding(
            label, orientation.cls, orientation.tilt_deg, orientation.roll_deg))
        return

    m = measure(frame, orientation.cls, host, nut.across_flats)
    record.findings += checker.check(label, orientation.cls, nut, m, settings)
    record.pocket = {"width": m.widths, "thickness": m.thickness, "depth": m.depth,
                     "seat_gaps": m.seat_gaps}
    if m.placement is not None:
        record.placement = m.placement.tolist()
        record.z_low, record.z_high = m.z_low, m.z_high
        record.roof_z, record.rim_z = m.roof_z, m.rim_z
        record.window = [m.z_high + settings.min_top_clearance_mm, m.roof_z]
    if m.box is not None:
        record.box = m.box


def preview_edges(snapshot: ModelSnapshot, limit: int = MAX_EDGE_SEGMENTS) -> list[list[float]]:
    """Feature edges of the printed parts as [x1, y1, z1, x2, y2, z2] rows in bed coordinates."""
    segments, angles = [], []
    for obj in snapshot.objects:
        for part in obj.parts:
            if naming.looks_like_nut(part.name):
                continue
            local, angle = feature_edges(part.vertices, part.triangles)  # once per part
            if len(local) == 0:
                continue
            for inst in obj.instances:
                matrix = inst.matrix @ part.matrix
                segments.append(apply_matrix(local.reshape(-1, 3), matrix).reshape(-1, 2, 3))
                angles.append(angle)
    if not segments:
        return []
    kept = limit_segments(np.concatenate(segments), np.concatenate(angles), limit)
    return np.round(kept.reshape(-1, 6), 3).tolist()
