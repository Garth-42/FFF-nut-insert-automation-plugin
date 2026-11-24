"""The heat-set half of the export step: from report records to placement.

docs/heatset-plan.md, "Export". The plugin runs the nut injection first and hands its
output here. Records come from heatsetcore.detect. This module sorts them into inserts
to place, inserts their checks refused, and inserts the printer cannot press (tilted or
inverted), then calls place.place once, with the one profile the print uses.
"""

from __future__ import annotations

from nutcore.library import Library
from nutcore.report import ERROR, WARNING

from . import profile
from .place import SUCCESS, InsertSpec, PlaceResult, place

UPRIGHT = "UPRIGHT"


def export(text: str, records, lib: Library, *, version: str = "",
           filament_type: str | None = None) -> PlaceResult:
    """Place the heat-set inserts among records (any kind) in the G-code text."""
    heat = [r for r in records if r.kind == "heatset"]
    if not heat:
        return PlaceResult(SUCCESS, "No heat-set inserts in the report.", text, [])
    specs, keys, refused, by_hand = [], [], [], []
    for r in heat:
        error = next((f for f in r.findings if f.level == ERROR), None)
        if error is not None:
            refused.append((r.label, error.code, error.message))
        elif r.cls != UPRIGHT or r.placement is None or not r.pocket:
            warning = next((f for f in r.findings if f.level == WARNING), None)
            by_hand.append((r.label, warning.code if warning else str(r.cls),
                            warning.message if warning else "not measured"))
        elif keys and r.key != keys[0]:             # detect_inserts already refuses these
            refused.append((r.label, "E_PROFILE", f"{r.label}: one heat-set tool per print, "
                            f"and this print already has HEATSET_{keys[0]} inserts."))
        else:
            specs.append(InsertSpec(label=r.label, x=r.placement[0], y=r.placement[1],
                                    z_top=r.z_high, hole_d=r.pocket["diameter"],
                                    bottom_z=r.pocket["bottom_z"]))
            keys.append(r.key)
    prof = _profile(lib, keys or [r.key for r in heat])
    return place(text, specs, prof, on_error=lib.settings.on_error, version=version,
                 filament_type=filament_type, refused=refused, by_hand=by_hand)


def _profile(lib: Library, keys) -> dict:
    """The profile of the print's inserts. detect_inserts allows one per print; a print
    with only unknown names still gets one, so its skipped inserts can be listed."""
    for key in keys:
        found = lib.heatset_profile(key)
        if found is not None:
            return found
    return lib.heatset[0] if lib.heatset else profile.default_profile()


def export_info(result: PlaceResult) -> dict:
    """What the export did with each insert, by label, for the report's export field."""
    info = {}
    for p in result.inserts:
        if p.block is not None:
            info[p.spec.label] = {"block": p.block, "z_top": p.z_top, "object": p.object,
                                  "after_line": p.line + 1}
        else:
            first = next((f for f in p.findings if f.level == ERROR), None)
            note = first or next(iter(p.findings), None)
            info[p.spec.label] = {"skipped": note.code if note else "not placed"}
    for label, code, _ in result.left_out:
        info.setdefault(label, {"skipped": code})
    return info
